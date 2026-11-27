#!/usr/bin/env python3
"""judge.py controls [--expect-fault]
judge.py answer --goal DIR --problem ID --kind proof|refutation|cut --answer FILE [--answer-sha256 HEX] [--submission ID]
judge.py corpus --goal DIR --corpus FILE

The Lean judge of Proving Ground. It runs Lean's own `lake comparator --paranoid` on one answer and
turns what the judge says into one of three findings:

    accepted   exit code 0 AND the judge's closing line
    rejected   exit code 1 AND one of the judge's own refusals (or the answer alone failing to build)
    fault      anything else: the finding says nothing about the answer

The exit code alone is never believed. A sandbox that cannot start also exits with 1, so `controls`
first judges a pair that must be accepted and a pair that must be refused; `answer` refuses to give
any finding but `fault` unless both behave.

`answer` reads the goal's manifests (proving-ground/*.toml), writes the challenge itself from the
names in them, screens and places the answer, and prints a verdict as JSON. `corpus` judges every
answer already in the goal (each must be accepted) and every dishonest file listed in the corpus
(each must draw the finding the corpus names).

Runs `lake` in the given directories and writes files inside the goal directory. It is meant for a
machine that is thrown away afterwards. PG_JUDGE_EXTRA_ARGS adds arguments to the judge; it exists
so the corpus can be run without a sandbox on files one wrote oneself, and no workflow sets it."""
import argparse, hashlib, json, os, re, shlex, shutil, subprocess, sys, tempfile, time, tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROLS = os.path.join(os.path.dirname(HERE), "controls")
OK_LINE = "Your solution is okay!"
REFUSALS = (("statement_mismatch", "Challenge and solution theorem statement do not match"),
            ("definition_mismatch", "Const does not match between challenge and target"),
            ("illegal_axiom", "Illegal axiom detected"))
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_']*(\.[A-Za-z_][A-Za-z0-9_']*)*")
ID = re.compile(r"[a-z][a-z0-9_]{0,62}")
HIDDEN = re.compile("[​-‏  ‪-‮⁠-⁤⁦-⁩﻿￹-￻\U000e0001-\U000e007f]")
MAX_ANSWER = 256 * 1024
EXTRA = shlex.split(os.environ.get("PG_JUDGE_EXTRA_ARGS", ""))
sha = lambda b: hashlib.sha256(b).hexdigest()


def run_judge(goal, challenge, solution, theorem, axioms, timeout=1500):
    """One run of the judge. Returns (outcome, reason_code, message, seconds, log tail)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"challenge_module": challenge, "solution_module": solution, "theorem_names": [theorem], "permitted_axioms": axioms}, f); cfg = f.name
    t0 = time.time()
    try:
        r = subprocess.run(["lake", "comparator", "--paranoid", "--config", cfg] + EXTRA, cwd=goal, capture_output=True, text=True, timeout=timeout)
        rc, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        rc, out = None, "the judge did not finish in %d seconds" % timeout
    finally:
        os.unlink(cfg)
    return classify(rc, out, challenge, solution, theorem) + (round(time.time() - t0, 1), out[-4000:])


def classify(rc, out, challenge, solution, theorem):
    lines = [l.rstrip() for l in out.split("\n") if l.strip() and not l.startswith("Exporting")]
    if rc == 0 and OK_LINE in out: return "accepted", "accepted", OK_LINE
    if rc == 1:
        for code, text in REFUSALS:
            hit = [l for l in lines if text in l]
            if hit: return "rejected", code, hit[0][:300]
        # The answer built, and then one or more of the judge's checkers refused the proof itself.
        said = lambda word: [m.group(1) for l in lines for m in [re.fullmatch(r"(.+) kernel %s the solution" % word, l)] if m]
        refused, passed = said("rejected"), said("accepts")
        if refused:
            if passed: return "rejected", "checkers_disagree", ("rejected by %s; accepted by %s" % (", ".join(refused), ", ".join(passed)))[:300]
            return "rejected", "checker_rejected", ("rejected by every checker that ran: %s" % ", ".join(refused))[:300]
        # The answer built but does not hold the theorem: the judge's exporter says so and stops.
        if ("Constant %s not found in environment" % theorem) in out and out.count("Build completed successfully") >= 2:
            return "rejected", "theorem_missing", "the answer does not declare %s" % theorem
        if "error: build failed" in out:
            failed = [l[2:].strip() for l in lines if l.startswith("- ")]
            if solution in failed and challenge not in failed:
                first = next((l for l in lines if l.startswith("error:") and "build failed" not in l and "Child exited" not in l), "the answer does not build")
                return "rejected", "build_failed", first[:300]
    if rc is None: return "fault", "timeout", lines[-1][:300] if lines else "timeout"
    tell = next((l for l in lines if "bwrap" in l), None) or next((l for l in reversed(lines) if l.startswith("error:")), lines[-1] if lines else "no output")
    return "fault", "fault", tell[:300]


def controls():
    """The judge on a pair that must be accepted and a pair that must be refused. Returns (ok, detail)."""
    ax = ["propext", "Quot.sound", "Classical.choice"]
    good = run_judge(CONTROLS, "Challenge", "Good", "Control.two_plus_two", ax, timeout=600)
    bad = run_judge(CONTROLS, "Challenge", "Bad", "Control.two_plus_two", ax, timeout=600)
    ok = good[0] == "accepted" and bad[:2] == ("rejected", "illegal_axiom")
    return ok, {"good": list(good[:3]), "bad": list(bad[:3])}


def manifest(goal, sub, ident):
    assert ID.fullmatch(ident), "not an identifier: %r" % ident
    m = tomllib.load(open(os.path.join(goal, "proving-ground", sub, ident + ".toml"), "rb"))
    assert m.get("id") == ident, "the manifest's id is not its file name"
    return m


def lean_name(x):
    assert isinstance(x, str) and NAME.fullmatch(x), "not a Lean name: %r" % (x,)
    return x


def plan(goal, problem, kind):
    """What to judge: (challenge module, challenge text, solution module, where the answer goes, theorem, axioms)."""
    g = tomllib.load(open(os.path.join(goal, "proving-ground", "goal.toml"), "rb"))
    stm, axioms = lean_name(g["statements"]), [lean_name(a) for a in g["permitted_axioms"]]
    if kind in ("proof", "refutation"):
        p = manifest(goal, "problems", problem); th, st = lean_name(p["theorem"]), lean_name(p["statement"])
        if kind == "refutation":
            assert p["kind"] == "settle", "only a settle problem can be refuted"
            return ("Problems.%s_neg" % problem, "import %s\n\ntheorem %s_neg : ¬ %s := sorry\n" % (stm, th, st), "Proofs.%s_neg" % problem, "Proofs/%s_neg.lean" % problem, th + "_neg", axioms)
        return ("Problems." + problem, "import %s\n\ntheorem %s : %s := sorry\n" % (stm, th, st), "Proofs." + problem, "Proofs/%s.lean" % problem, th, axioms)
    assert kind == "cut", "unknown kind of answer: %r" % kind
    c = manifest(goal, "cuts", problem); parent = manifest(goal, "problems", c["parent"])
    hyps = " ".join("(h%d : %s)" % (i + 1, lean_name(manifest(goal, "problems", k)["statement"])) for i, k in enumerate(c["children"]))
    th = lean_name(c["theorem"])
    return ("Problems.cut_" + problem, "import %s\n\ntheorem %s %s : %s := sorry\n" % (stm, th, hyps, lean_name(parent["statement"])), "Cuts." + problem, "Cuts/%s.lean" % problem, th, axioms)


def screen(raw, theorem):
    """The form screen. Returns a reason for refusal, or None. Soundness never rests on it."""
    if len(raw) > MAX_ANSWER: return "too_large", "the file is larger than %d bytes" % MAX_ANSWER
    try: text = raw.decode("utf-8")
    except UnicodeDecodeError: return "not_utf8", "the file is not valid UTF-8"
    if HIDDEN.search(text): return "hidden_characters", "the file holds direction-changing or zero-width characters"
    if not re.search(r"^\s*(?:theorem|lemma)\s+%s(?![A-Za-z0-9_'.])" % re.escape(theorem), text, re.M):
        return "theorem_missing", "the file does not declare %s" % theorem
    return None


def judge_answer(goal, problem, kind, raw, restore=False):
    ch_mod, ch_text, so_mod, rel, theorem, axioms = plan(goal, problem, kind)
    out = {"problem": problem, "answer_kind": kind, "theorem": theorem, "challenge_sha256": sha(ch_text.encode()), "answer_sha256": sha(raw)}
    bad = screen(raw, theorem)
    if bad: return dict(out, outcome="rejected", reason_code=bad[0], message=bad[1], seconds=0, log_tail="")
    ch_path, an_path = os.path.join(goal, ch_mod.replace(".", "/") + ".lean"), os.path.join(goal, rel)
    kept = open(an_path, "rb").read() if restore and os.path.exists(an_path) else None
    os.makedirs(os.path.dirname(ch_path), exist_ok=True); os.makedirs(os.path.dirname(an_path), exist_ok=True)
    open(ch_path, "w", encoding="utf-8").write(ch_text); open(an_path, "wb").write(raw)
    try:
        outcome, code, message, seconds, tail = run_judge(goal, ch_mod, so_mod, theorem, axioms)
    finally:
        if restore:
            if kept is None: os.unlink(an_path)
            else: open(an_path, "wb").write(kept)
    return dict(out, outcome=outcome, reason_code=code, message=message, seconds=seconds, log_tail=tail)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("controls"); c.add_argument("--expect-fault", action="store_true")
    a = sub.add_parser("answer")
    for n in ("--goal", "--problem", "--kind", "--answer"): a.add_argument(n, required=True)
    a.add_argument("--answer-sha256", default=""); a.add_argument("--submission", default="")
    k = sub.add_parser("corpus"); k.add_argument("--goal", required=True); k.add_argument("--corpus", required=True)
    A = ap.parse_args()

    if A.cmd == "controls":
        ok, detail = controls(); print(json.dumps(detail, indent=1))
        if A.expect_fault:
            if detail["good"][0] == "accepted": print("the sandbox starts on this machine as it comes: nothing to test here"); sys.exit(0)
            sys.exit(0 if detail["good"][0] == "fault" and detail["bad"][0] == "fault" else "a judge that cannot start must read as a fault, and it read as %s / %s" % (detail["good"][0], detail["bad"][0]))
        sys.exit(0 if ok else "the controls misbehaved: the judge is not working on this machine")

    goal = os.path.abspath(A.goal)
    if A.cmd == "answer":
        raw = open(A.answer, "rb").read()
        env = {v: os.environ.get(e) for v, e in (("repository", "GITHUB_REPOSITORY"), ("sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("workflow_ref", "GITHUB_WORKFLOW_REF"), ("event", "GITHUB_EVENT_NAME"), ("actor", "GITHUB_ACTOR"), ("triggering_actor", "GITHUB_TRIGGERING_ACTOR"))}
        v = {"kind": "proving-ground.verdict.v1", "submission": A.submission, "checker": env,
             "goal": {"repository": os.environ.get("PG_GOAL_REPOSITORY"), "commit": os.environ.get("PG_GOAL_COMMIT")},
             "judge": {"tool": "lake comparator --paranoid", "lean": subprocess.run(["lean", "--version"], capture_output=True, text=True).stdout.strip(), "sandbox_route": os.environ.get("PG_SANDBOX_ROUTE")}}
        if A.answer_sha256 and A.answer_sha256 != sha(raw):
            v.update(outcome="fault", reason_code="answer_hash", message="the fetched answer is not the one that was named", answer_sha256=sha(raw))
        else:
            ok, detail = controls(); v["controls"] = detail
            if not ok: v.update(outcome="fault", reason_code="controls", message="the judge is not working on this machine", answer_sha256=sha(raw))
            else:
                try: v.update(judge_answer(goal, A.problem, A.kind, raw))
                except (AssertionError, KeyError, OSError, tomllib.TOMLDecodeError) as e: v.update(outcome="fault", reason_code="goal", message=("%s: %s" % (type(e).__name__, e))[:300], answer_sha256=sha(raw))
        print(json.dumps(v, indent=1)); return

    # corpus: every answer in the goal must be accepted; every dishonest file must draw its named finding
    ok, detail = controls()
    if not ok: sys.exit("the controls misbehaved: %s" % json.dumps(detail))
    wrong, rows = 0, []
    def row(label, got, want):
        nonlocal wrong
        good = (got["outcome"], got["reason_code"]) == tuple(want); wrong += not good
        print("%-5s %-46s %-9s %-20s %5.1fs  %s" % ("ok" if good else "WRONG", label, got["outcome"], got["reason_code"], got["seconds"], "" if good else "wanted %s/%s: %s" % (want[0], want[1], got["message"][:110])), flush=True)
    for f in sorted(os.listdir(os.path.join(goal, "Proofs"))):
        pid = f[:-5]; kind = "refutation" if pid.endswith("_neg") else "proof"; pid = pid[:-4] if kind == "refutation" else pid
        row("honest %s of %s" % (kind, pid), judge_answer(goal, pid, kind, open(os.path.join(goal, "Proofs", f), "rb").read(), restore=True), ("accepted", "accepted"))
    for f in sorted(os.listdir(os.path.join(goal, "Cuts"))) if os.path.isdir(os.path.join(goal, "Cuts")) else []:
        row("honest cut %s" % f[:-5], judge_answer(goal, f[:-5], "cut", open(os.path.join(goal, "Cuts", f), "rb").read(), restore=True), ("accepted", "accepted"))
    C = json.load(open(A.corpus, encoding="utf-8")); base = os.path.dirname(os.path.abspath(A.corpus))
    for e in C["answers"]:
        row("corpus " + e["file"], judge_answer(goal, e["problem"], e["kind"], open(os.path.join(base, e["file"]), "rb").read(), restore=True), (e["outcome"], e["reason_code"]))
    print("%d wrong" % wrong); sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
