#!/usr/bin/env python3
"""judge.py controls [--expect-fault]
judge.py challenge --goal DIR --problem ID --kind KIND --out DIR
judge.py answer --goal DIR --problem ID --kind KIND --answer FILE --out DIR [--answer-sha256 HEX] [--budget SECONDS]
judge.py verdict --plan FILE --fingerprint HEX --challenge FILE --answer-dir DIR [--jobs challenge=RESULT,answer=RESULT]
                 [--submission ID] [--answer-sha256 HEX] [--budget SECONDS]
judge.py corpus --goal DIR --corpus FILE

The Lean judge of Proving Ground, in three steps. The check workflow runs them as three jobs on
three machines.

    challenge   builds the goal's library and one challenge, with no answer present, and exports
                the challenge with Lean's own exporter. The export's SHA-256 is the problem's
                fingerprint: it changes when anything the statement means changes.
    answer      builds one answer inside a sandbox with no network, within a time budget, and
                exports it. This is the only step that runs submitted code, and nothing it reports
                in the answer's favour is believed. It hands on an export, or the reason there is
                none.
    verdict     runs Lean's own `lake comparator --paranoid` on the two exports and nothing else.
                It builds nothing and runs no submitted code.

A finding is one of three:

    accepted   in the verdict step: every control behaved, the judge exited with 0, and its output
               held exactly its own lines, ending with its closing line
    rejected   every control behaved, and the answer was not accepted
    fault      a control misbehaved, or something the answer never touched could not be fetched or
               built. A fault says nothing about the answer

Whether a finding is a fault is decided by the health of the machine: a pair that must be accepted
is judged before the answer is touched and again after it. The exit code alone is never believed,
since a sandbox that cannot start also exits with 1.

The judge's output is read on one rule: what is being judged can add text to it, and can take none
away. So a reading is believed only when each of the judge's own lines appears exactly once and in
the judge's order. Anything else is `unrecognised`, which is a rejection.

`corpus` runs all three steps on one machine: every answer already in the goal must be accepted, and
every file the corpus lists must draw the finding the corpus names.

Runs `lake` and `bwrap`, and writes files inside the goal directory and the output directory. It is
meant for a machine that is thrown away afterwards. PG_JUDGE_NO_SANDBOX=1 runs everything without a
sandbox. It exists so the corpus can be run on files one wrote oneself, on a machine where the
sandbox cannot start, and no workflow sets it."""
import argparse, hashlib, json, os, re, shutil, signal, subprocess, sys, tempfile, time, tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROLS = os.path.join(os.path.dirname(HERE), "controls")
NO_SANDBOX = os.environ.get("PG_JUDGE_NO_SANDBOX") == "1"
OK_LINE = "Your solution is okay!"
STANDARD_AXIOMS = ["propext", "Quot.sound", "Classical.choice"]
# The judge's checkers, in the order it runs them (Lake/CLI/Check.lean in the Lean 4.36.0 release).
KERNELS = ("Lean paranoid", "lean4lean", "nanoda", "con-leche", "con-ron", "Lean default")
# The judge's refusals by comparison. Each is how the first line of its error output begins.
COMPARE = (("statement_mismatch", "Challenge and solution theorem statement do not match: '"),
           ("statement_mismatch", "Challenge and solution constant kind don't match: '"),
           ("statement_mismatch", "Solution constant is not a theorem: '"),
           ("definition_mismatch", "Const does not match between challenge and target '"),
           ("illegal_axiom", "Illegal axiom detected: '"),
           ("theorem_missing", "Const not found in solution: '"))
# What the judge always exports and compares, beside the theorem and the permitted axioms. A
# release that compares more makes every honest answer fail the corpus, which is the alarm.
PRIMITIVES = ("Nat.add Nat.sub Nat.mul Nat.pow Nat.gcd Nat.div Nat.mod Nat.beq Nat.ble Nat.land Nat.lor Nat.xor Nat.shiftLeft Nat.shiftRight "
              "String.ofList Char.ofNat List eagerReduce Nat String String.mk Char optParam autoParam semiOutParam outParam").split()
QUOT = ["Quot", "Quot.mk", "Quot.lift", "Quot.ind"]
# The only reasons the answer step may give for a rejection. Each can only count against the answer.
ANSWER_REASONS = ("build_failed", "theorem_missing", "export_failed", "timeout", "too_large", "not_utf8", "hidden_characters")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_']*(\.[A-Za-z_][A-Za-z0-9_']*)*")
ID = re.compile(r"[a-z][a-z0-9_]{0,62}")
HIDDEN = re.compile("[​-‏  ‪-‮⁠-⁤⁦-⁩﻿￹-￻\U000e0001-\U000e007f]")
MAX_ANSWER = 256 * 1024
GOAL_ERRORS = (AssertionError, KeyError, OSError, tomllib.TOMLDecodeError)
sha = lambda b: hashlib.sha256(b).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def run(cmd, cwd, timeout, env=None, stdout_to=None):
    """One command in a process group of its own, the whole group killed at the time limit.
    Returns (exit code, or None at the limit; stdout; stderr; seconds)."""
    t0 = time.time(); sink = open(stdout_to, "wb") if stdout_to else subprocess.PIPE
    try:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = p.communicate(timeout=timeout); rc = p.returncode
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            out, err = p.communicate(); rc = None
    finally:
        if stdout_to: sink.close()
    text = lambda b: (b or b"").decode("utf-8", "replace")
    return rc, text(out), text(err), round(time.time() - t0, 1)


def in_sandbox(cmd, goal, timeout, stdout_to=None):
    """A command on the goal with no network, a read-only system, an empty home and a process space
    of its own. It can write only the goal's .lake directory. The arguments are the ones Lean's own
    judge gives bwrap (Lake/CLI/Check.lean in the 4.36.0 release)."""
    env = {"PATH": os.environ["PATH"], "LEAN_ABORT_ON_PANIC": "1"}
    dot = os.path.join(goal, ".lake"); os.makedirs(dot, exist_ok=True)
    if NO_SANDBOX: return run(cmd, goal, timeout, env=dict(os.environ, **env), stdout_to=stdout_to)
    lean = os.path.dirname(os.path.dirname(os.path.realpath(shutil.which("lake"))))
    a = ["bwrap", "--ro-bind", "/", "/", "--tmpfs", "/home", "--tmpfs", "/root", "--tmpfs", "/run/user", "--tmpfs", "/tmp", "--dir", "/tmp/home",
         "--dev", "/dev", "--proc", "/proc", "--clearenv", "--tmpfs", "/run", "--tmpfs", "/var",
         "--ro-bind", goal, goal, "--ro-bind", lean, lean, "--bind", dot, dot]
    for k, v in env.items(): a += ["--setenv", k, v]
    a += ["--setenv", "HOME", "/tmp/home", "--unshare-all", "--die-with-parent", "--new-session", "--chdir", goal, "--"]
    return run(a + cmd, goal, timeout, stdout_to=stdout_to)


def comparator(cwd, challenge, solution, theorem, axioms, timeout, exports=None):
    """One run of Lean's judge. With `exports` it judges two export files and builds nothing."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"challenge_module": challenge, "solution_module": solution, "theorem_names": [theorem], "permitted_axioms": axioms}, f); cfg = f.name
    cmd = ["lake", "comparator", "--paranoid", "--config", cfg]
    if exports: cmd += ["--challenge-from-export", exports[0], "--solution-from-export", exports[1]]
    if NO_SANDBOX: cmd.append("--inadvisably-no-sandbox")
    try: return run(cmd, cwd, timeout)
    finally: os.unlink(cfg)


def read_strict(rc, out, err, theorem):
    """Reads one run of the judge on two exports. Returns (outcome, reason code, message).
    Names in an export can reach the output through a checker's own messages, so every line of the
    judge's own must be there exactly once and in its order, or the reading is `unrecognised`."""
    if rc is None: return "rejected", "timeout", "the judge's checkers did not finish inside the time budget"
    said = []
    for line in out.split("\n"):
        line = line.rstrip("\r")
        for word, pattern in (("run", r"Running (.+) kernel on solution"), ("accepts", r"(.+) kernel accepts the solution"),
                              ("rejected", r"(.+) kernel rejected the solution"), ("error", r"Error while interacting with (.+) kernel")):
            m = re.fullmatch(pattern, line)
            if m: said.append((word, m.group(1))); break
        else:
            if line == OK_LINE: said.append(("ok", ""))
    errs = [l for l in err.split("\n") if l.strip() and not l.startswith("WARNING: Sandbox disabled")]
    lost = ("rejected", "unrecognised", "the judge's output is not one of its own findings (exit code %s)" % rc)
    if not said:
        # Nothing ran but the comparison. Its refusal is the first line of the error output.
        if rc == 1 and errs:
            for code, start in COMPARE:
                if errs[0].startswith("error: " + start):
                    if code == "theorem_missing" and errs[0] != "error: %s%s'" % (start, theorem): return lost
                    return "rejected", code, errs[0][:300]
        return lost
    closed = said[-1] == ("ok", ""); body = said[:-1] if closed else said
    if len(body) != 2 * len(KERNELS): return lost
    for i, k in enumerate(KERNELS):
        if body[2 * i] != ("run", k) or body[2 * i + 1] not in (("accepts", k), ("rejected", k)): return lost
    refused = [k for word, k in body if word == "rejected"]; passed = [k for word, k in body if word == "accepts"]
    if not refused: return ("accepted", "accepted", OK_LINE) if rc == 0 and closed else lost
    if closed or rc != 1: return lost
    if passed: return "rejected", "checkers_disagree", ("rejected by %s; accepted by %s" % (", ".join(refused), ", ".join(passed)))[:300]
    return "rejected", "checker_rejected", "rejected by every checker: %s" % ", ".join(refused)


def control(solution):
    """The judge on a pair of the checker's own files. Returns [outcome, reason code, message]."""
    rc, out, err, _ = comparator(CONTROLS, "Challenge", solution, "Control.two_plus_two", STANDARD_AXIOMS, 600)
    if rc == 0 and OK_LINE in out: return ["accepted", "accepted", OK_LINE]
    lines = [l.strip() for l in (out + err).split("\n") if l.strip()]
    if rc == 1 and any(l.startswith("error: Illegal axiom detected: 'sorryAx'") for l in lines): return ["rejected", "illegal_axiom", "error: Illegal axiom detected: 'sorryAx'"]
    tell = next((l for l in lines if "bwrap" in l), None) or next((l for l in reversed(lines) if l.startswith("error:")), lines[-1] if lines else "no output")
    return ["fault", "fault", tell[:300]]


def controls(after=False):
    """Before an answer: a pair that must be accepted and a pair that must be refused. After it: the
    first pair again. Returns (ok, detail)."""
    good = control("Good")
    if after: return good[0] == "accepted", {"good": good}
    bad = control("Bad")
    return good[0] == "accepted" and bad[:2] == ["rejected", "illegal_axiom"], {"good": good, "bad": bad}


def manifest(goal, sub, ident):
    assert ID.fullmatch(ident), "not an identifier: %r" % ident
    m = tomllib.load(open(os.path.join(goal, "proving-ground", sub, ident + ".toml"), "rb"))
    assert m.get("id") == ident, "the manifest's id is not its file name"
    return m


def lean_name(x):
    assert isinstance(x, str) and NAME.fullmatch(x), "not a Lean name: %r" % (x,)
    return x


def plan(goal, problem, kind):
    """What to judge, written from the names in the goal's manifests and nothing else."""
    g = tomllib.load(open(os.path.join(goal, "proving-ground", "goal.toml"), "rb"))
    stm, axioms = lean_name(g["statements"]), [lean_name(a) for a in g["permitted_axioms"]]
    mk = lambda cm, text, sm, rel, th: {"problem": problem, "answer_kind": kind, "challenge_module": cm, "challenge_text": text, "solution_module": sm, "answer_path": rel, "theorem": th, "axioms": axioms}
    if kind in ("proof", "refutation"):
        p = manifest(goal, "problems", problem); th, st = lean_name(p["theorem"]), lean_name(p["statement"])
        if kind == "refutation":
            assert p["kind"] == "settle", "only a settle problem can be refuted"
            return mk("Problems.%s_neg" % problem, "import %s\n\ntheorem %s_neg : ¬ %s := sorry\n" % (stm, th, st), "Proofs.%s_neg" % problem, "Proofs/%s_neg.lean" % problem, th + "_neg")
        return mk("Problems." + problem, "import %s\n\ntheorem %s : %s := sorry\n" % (stm, th, st), "Proofs." + problem, "Proofs/%s.lean" % problem, th)
    assert kind == "cut", "unknown kind of answer: %r" % kind
    c = manifest(goal, "cuts", problem); parent = manifest(goal, "problems", c["parent"])
    hyps = " ".join("(h%d : %s)" % (i + 1, lean_name(manifest(goal, "problems", k)["statement"])) for i, k in enumerate(c["children"]))
    return mk("Problems.cut_" + problem, "import %s\n\ntheorem %s %s : %s := sorry\n" % (stm, lean_name(c["theorem"]), hyps, lean_name(parent["statement"])), "Cuts." + problem, "Cuts/%s.lean" % problem, lean_name(c["theorem"]))


def export(goal, module, p, path):
    """Lean's own exporter on one module: the theorem, the axioms, and all they reach."""
    decls = (QUOT if "Quot.sound" in p["axioms"] else []) + [p["theorem"]] + p["axioms"] + PRIMITIVES
    return in_sandbox(["lake", "env", "leanexport", module, "--"] + decls, goal, 900, stdout_to=path)


def first_error(text, default):
    return next((l.strip() for l in text.split("\n") if l.strip().startswith("error:") and "build failed" not in l), default)[:300]


def make_challenge(goal, problem, kind, out):
    """The challenge step. Returns the plan with the fingerprint; the export is <out>/challenge.ndjson.
    Any failure here is the goal's, and raises."""
    p = plan(goal, problem, kind); t0 = time.time(); os.makedirs(out, exist_ok=True)
    path = os.path.join(goal, p["challenge_module"].replace(".", "/") + ".lean")
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w", encoding="utf-8").write(p["challenge_text"])
    rc, o, e, _ = in_sandbox(["lake", "build", p["challenge_module"]], goal, 1500)
    assert rc == 0, "the challenge does not build (exit %s): %s" % (rc, first_error(o + e, (o + e).strip()[-300:]))
    exp = os.path.join(out, "challenge.ndjson"); rc, _, e, _ = export(goal, p["challenge_module"], p, exp)
    assert rc == 0, "the challenge could not be exported (exit %s): %s" % (rc, e.strip()[-300:])
    return dict(p, fingerprint=sha_file(exp), export_bytes=os.path.getsize(exp), seconds=round(time.time() - t0, 1))


def screen(raw, theorem):
    """The form screen. Returns a reason for refusal, or None. Soundness never rests on it."""
    if len(raw) > MAX_ANSWER: return "too_large", "the file is larger than %d bytes" % MAX_ANSWER
    try: text = raw.decode("utf-8")
    except UnicodeDecodeError: return "not_utf8", "the file is not valid UTF-8"
    if HIDDEN.search(text): return "hidden_characters", "the file holds direction-changing or zero-width characters"
    if not re.search(r"^\s*(?:theorem|lemma)\s+%s(?![A-Za-z0-9_'.])" % re.escape(theorem), text, re.M):
        return "theorem_missing", "the file does not declare %s" % theorem
    return None


def build_answer(goal, problem, kind, raw, budget, out, restore=False):
    """The answer step. Returns a report whose state is `exported` (the export is
    <out>/solution.ndjson) or `rejected`, with a reason from ANSWER_REASONS."""
    p = plan(goal, problem, kind); os.makedirs(out, exist_ok=True)
    rep = {"problem": problem, "answer_kind": kind, "theorem": p["theorem"], "answer_sha256": sha(raw)}
    no = lambda code, message, secs=0, tail="": dict(rep, state="rejected", reason_code=code, message=message[:300], seconds=secs, log_tail=tail[-4000:])
    bad = screen(raw, p["theorem"])
    if bad: return no(*bad)
    path = os.path.join(goal, p["answer_path"]); kept = open(path, "rb").read() if restore and os.path.exists(path) else None
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "wb").write(raw)
    try:
        rc, o, e, secs = in_sandbox(["lake", "build", p["solution_module"]], goal, budget); text = o + e
        if rc is None: return no("timeout", "the answer did not build inside the time budget of %d seconds" % budget, secs, text)
        if rc != 0: return no("build_failed", first_error(text, "the answer does not build"), secs, text)
        exp = os.path.join(out, "solution.ndjson"); rc, _, e2, s2 = export(goal, p["solution_module"], p, exp)
        if rc != 0:
            if os.path.exists(exp): os.unlink(exp)
            if rc is None: return no("timeout", "the answer could not be exported in time", secs + s2, e2)
            if ("Constant %s not found" % p["theorem"]) in e2: return no("theorem_missing", "the answer does not declare %s" % p["theorem"], secs + s2, e2)
            return no("export_failed", "the answer built, and what it built could not be exported", secs + s2, e2)
        return dict(rep, state="exported", export_bytes=os.path.getsize(exp), seconds=round(secs + s2, 1), log_tail=text[-4000:])
    finally:
        if restore:
            if kept is None: os.unlink(path)
            else: open(path, "wb").write(kept)


def judge_exports(p, challenge, solution, budget):
    """The verdict step's judgement: Lean's judge on two exports, in an empty directory.
    Returns (outcome, reason code, message, seconds, log tail)."""
    empty = tempfile.mkdtemp(prefix="pg-verdict-")
    try: rc, o, e, secs = comparator(empty, p["challenge_module"], p["solution_module"], p["theorem"], p["axioms"], budget, exports=(os.path.abspath(challenge), os.path.abspath(solution)))
    finally: shutil.rmtree(empty, ignore_errors=True)
    return read_strict(rc, o, e, p["theorem"]) + (secs, (o + e)[-4000:])


def lean_version():
    try: return subprocess.run(["lean", "--version"], capture_output=True, text=True).stdout.strip()
    except OSError: return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("controls", allow_abbrev=False); c.add_argument("--expect-fault", action="store_true")
    h = sub.add_parser("challenge", allow_abbrev=False)
    for n in ("--goal", "--problem", "--kind", "--out"): h.add_argument(n, required=True)
    a = sub.add_parser("answer", allow_abbrev=False)
    for n in ("--goal", "--problem", "--kind", "--answer", "--out"): a.add_argument(n, required=True)
    a.add_argument("--answer-sha256", default=""); a.add_argument("--budget", type=int, default=900)
    v = sub.add_parser("verdict", allow_abbrev=False)
    for n in ("--plan", "--fingerprint", "--challenge", "--answer-dir"): v.add_argument(n, required=True)
    v.add_argument("--jobs", default=""); v.add_argument("--submission", default=""); v.add_argument("--answer-sha256", default=""); v.add_argument("--budget", type=int, default=900)
    k = sub.add_parser("corpus", allow_abbrev=False); k.add_argument("--goal", required=True); k.add_argument("--corpus", required=True)
    A = ap.parse_args()

    if A.cmd == "controls":
        ok, detail = controls(); print(json.dumps(detail, indent=1))
        if A.expect_fault:
            if detail["good"][0] == "accepted": print("the sandbox starts on this machine as it comes: nothing to test here"); sys.exit(0)
            sys.exit(0 if detail["good"][0] == "fault" and detail["bad"][0] == "fault" else "a judge that cannot start must read as a fault, and it read as %s / %s" % (detail["good"][0], detail["bad"][0]))
        sys.exit(0 if ok else "the controls misbehaved: the judge is not working on this machine")

    if A.cmd == "challenge":
        # Trusted with the fingerprint: it is given the goal and never the answer.
        p = make_challenge(os.path.abspath(A.goal), A.problem, A.kind, A.out)
        small = {x: p[x] for x in ("problem", "answer_kind", "challenge_module", "solution_module", "theorem", "axioms", "fingerprint")}
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("fingerprint=%s\nplan=%s\ntoolchain=%s\n" % (p["fingerprint"], json.dumps(small), open(os.path.join(A.goal, "lean-toolchain"), encoding="utf-8").read().strip()))
        print(json.dumps(dict(small, export_bytes=p["export_bytes"], seconds=p["seconds"]), indent=1)); return

    if A.cmd == "answer":
        # Not trusted: it runs the answer. Its report is believed only where it counts against the answer.
        raw = open(A.answer, "rb").read(); os.makedirs(A.out, exist_ok=True)
        rep = {"kind": "proving-ground.answer-report.v1", "answer_sha256": sha(raw), "sandbox_route": os.environ.get("PG_SANDBOX_ROUTE")}
        fault = lambda code, message: rep.update(state="fault", reason_code=code, message=message[:300])
        if A.answer_sha256 and A.answer_sha256 != sha(raw): fault("answer_hash", "the fetched answer is not the one that was named")
        else:
            ok, before = controls(); rep["controls"] = before
            if not ok: fault("controls", "the judge is not working on this machine")
            else:
                try: rep.update(build_answer(os.path.abspath(A.goal), A.problem, A.kind, raw, A.budget, A.out))
                except GOAL_ERRORS as e: fault("goal", "%s: %s" % (type(e).__name__, e))
                ok, after = controls(after=True); rep["controls_after"] = after
                if not ok: fault("controls_after", "the judge stopped working on this machine while the answer was built")
        json.dump(rep, open(os.path.join(A.out, "answer.json"), "w", encoding="utf-8"), indent=1)
        print(rep["state"], rep.get("reason_code", ""), "|", rep.get("message", "")); return

    if A.cmd == "verdict":
        # Trusted with the finding: it runs the judge on two exports, and none of the answer.
        env = {x: os.environ.get(e) for x, e in (("repository", "GITHUB_REPOSITORY"), ("sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("workflow_ref", "GITHUB_WORKFLOW_REF"), ("event", "GITHUB_EVENT_NAME"), ("actor", "GITHUB_ACTOR"), ("triggering_actor", "GITHUB_TRIGGERING_ACTOR"))}
        jobs = dict(x.split("=", 1) for x in A.jobs.split(",") if "=" in x)
        V = {"kind": "proving-ground.verdict.v2", "submission": A.submission, "checker": env, "jobs": jobs,
             "goal": {"repository": os.environ.get("PG_GOAL_REPOSITORY"), "commit": os.environ.get("PG_GOAL_COMMIT")},
             "judge": {"tool": "lake comparator --paranoid, from two exports", "lean": lean_version(), "sandbox_route": os.environ.get("PG_SANDBOX_ROUTE")},
             "answer_sha256": A.answer_sha256, "fingerprint": A.fingerprint or None}
        fault = lambda code, message: V.update(outcome="fault", reason_code=code, message=message[:300])
        report = None
        try: report = json.load(open(os.path.join(A.answer_dir, "answer.json"), encoding="utf-8"))
        except (OSError, ValueError): pass
        solution = os.path.join(A.answer_dir, "solution.ndjson")
        if jobs.get("challenge", "success") != "success": fault("challenge_job", "the goal's challenge could not be built and exported")
        elif not os.path.isfile(A.challenge) or sha_file(A.challenge) != A.fingerprint: fault("challenge_export", "the challenge's export is not the one the challenge job made")
        elif jobs.get("answer", "success") != "success" or not isinstance(report, dict): fault("answer_job", "the answer job did not finish")
        else:
            p = json.load(open(A.plan, encoding="utf-8")); V.update(problem=p["problem"], answer_kind=p["answer_kind"], theorem=p["theorem"])
            V["answer_job"] = {x: report.get(x) for x in ("state", "reason_code", "message", "answer_sha256", "seconds", "export_bytes", "sandbox_route")}
            ok, before = controls(); V["controls"] = before
            if not ok: fault("controls", "the judge is not working on this machine")
            elif A.answer_sha256 and report.get("answer_sha256") != A.answer_sha256: fault("answer_hash", "the answer job did not build the answer that was named")
            elif report.get("state") == "fault": fault(str(report.get("reason_code"))[:40], "the answer job: %s" % report.get("message"))
            elif report.get("state") == "rejected" and report.get("reason_code") in ANSWER_REASONS:
                V.update(outcome="rejected", reason_code=report["reason_code"], message=str(report.get("message"))[:300], decided_by="answer job", log_tail=str(report.get("log_tail", ""))[-4000:])
            elif report.get("state") == "exported" and os.path.isfile(solution):
                outcome, code, message, secs, tail = judge_exports(p, A.challenge, solution, A.budget)
                V.update(outcome=outcome, reason_code=code, message=message, decided_by="verdict job", seconds=secs, log_tail=tail)
            else: fault("answer_report", "the answer job's report could not be read")
            if V["outcome"] != "fault":
                ok, after = controls(after=True); V["controls_after"] = after
                if not ok: fault("controls_after", "the judge stopped working on this machine")
        print(json.dumps(V, indent=1)); return

    # corpus: the three steps on one machine
    goal = os.path.abspath(A.goal); ok, detail = controls()
    if not ok: sys.exit("the controls misbehaved: %s" % json.dumps(detail))
    work = tempfile.mkdtemp(prefix="pg-corpus-"); made, wrong, n = {}, 0, 0
    def one(label, problem, kind, raw, want, budget=900, isolate=False):
        nonlocal wrong, n
        n += 1; key = (problem, kind)
        if key not in made:
            made[key] = make_challenge(goal, problem, kind, os.path.join(work, "c%d" % len(made)))
            print("      challenge %-32s fingerprint %s  export %d bytes  %.1fs" % ("%s (%s)" % key, made[key]["fingerprint"][:16], made[key]["export_bytes"], made[key]["seconds"]), flush=True)
        p = made[key]; out = os.path.join(work, "a%d" % n); g = goal
        if isolate: g = os.path.join(work, "g%d" % n); shutil.copytree(goal, g, symlinks=True)
        rep = build_answer(g, problem, kind, raw, budget, out, restore=True)
        if rep["state"] == "exported":
            outcome, code, message, secs, _ = judge_exports(p, os.path.join(work, "c%d" % list(made).index(key), "challenge.ndjson"), os.path.join(out, "solution.ndjson"), budget)
            secs += rep["seconds"]
        else: outcome, code, message, secs = "rejected", rep["reason_code"], rep["message"], rep["seconds"]
        if isolate: shutil.rmtree(g, ignore_errors=True)
        good = (outcome, code) == tuple(want); wrong += not good
        print("%-5s %-46s %-9s %-20s %5.1fs  %s" % ("ok" if good else "WRONG", label, outcome, code, secs, "" if good else "wanted %s/%s: %s" % (want[0], want[1], message[:110])), flush=True)
    for f in sorted(os.listdir(os.path.join(goal, "Proofs"))):
        pid = f[:-5]; kind = "refutation" if pid.endswith("_neg") else "proof"; pid = pid[:-4] if kind == "refutation" else pid
        one("honest %s of %s" % (kind, pid), pid, kind, open(os.path.join(goal, "Proofs", f), "rb").read(), ("accepted", "accepted"))
    for f in sorted(os.listdir(os.path.join(goal, "Cuts"))) if os.path.isdir(os.path.join(goal, "Cuts")) else []:
        one("honest cut %s" % f[:-5], f[:-5], "cut", open(os.path.join(goal, "Cuts", f), "rb").read(), ("accepted", "accepted"))
    C = json.load(open(A.corpus, encoding="utf-8")); base = os.path.dirname(os.path.abspath(A.corpus))
    for e in C["answers"]:
        if e.get("needs_sandbox") and NO_SANDBOX: print("skip  corpus %-39s it tests the sandbox, which is off" % e["file"], flush=True); continue
        one("corpus " + e["file"], e["problem"], e["kind"], open(os.path.join(base, e["file"]), "rb").read(), (e["outcome"], e["reason_code"]), budget=e.get("budget", 900), isolate=bool(e.get("isolate")))
    ok, after = controls(after=True); shutil.rmtree(work, ignore_errors=True)
    if not ok: sys.exit("the judge stopped working on this machine during the corpus: %s" % json.dumps(after))
    print("%d wrong" % wrong); sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
