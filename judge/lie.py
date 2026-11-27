#!/usr/bin/env python3
"""lie.py make <lie> --goal DIR --out DIR
lie.py plant --out DIR --submission ID
lie.py expect <lie> --verdict-dir DIR

A test of the check workflow against an answer job that lies. It is used only by the `lies`
workflow, which runs a real challenge job and a real verdict job around a dishonest job in the
answer's place. The lies:

    honest                  no lie: an honest answer, built as the answer job builds it
    forged-export           reports the named answer as exported, and hands over another proof's export
    forged-fault            reports that the machine's controls failed, to get a fault and not a rejection
    overwrites-challenge    replaces the challenge's export in the run's store of files
    plants-verdict-before   puts an accepting verdict in the store before the verdict job runs
    plants-verdict-after    replaces the verdict in the store after the verdict job has run

`make` writes what the dishonest job hands on. `plant` writes an accepting verdict. `expect` plays
the consumer of verdicts: it checks the token that should vouch for the verdict, and that the run
ended as that lie must end. Reads and writes files in the directories given. `make` runs `lake`."""
import argparse, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import judge  # noqa: E402
from verify_token import KEYS, check  # noqa: E402

ROOT = os.path.dirname(HERE)
# lie: (the answer the run names; is the verdict vouched for; outcome; reason code; kind of fault)
LIES = {
    "honest": ("goal:Proofs/xor2_le_4.lean", True, "accepted", "accepted", None),
    "forged-export": ("goal:Proofs/xor2_le_4.lean", True, "rejected", "theorem_missing", None),
    "forged-fault": ("goal:Proofs/xor2_le_4.lean", True, "fault", "controls", "answer_side"),
    "overwrites-challenge": ("goal:Proofs/xor2_le_4.lean", True, "fault", "challenge_export", "tampering"),
    "plants-verdict-before": ("corpus/sorry.lean", True, "rejected", "illegal_axiom", None),
    "plants-verdict-after": ("corpus/sorry.lean", False, None, None, None),
}


def named_answer(lie, goal):
    where = LIES[lie][0]
    return open(os.path.join(goal, where[5:]) if where.startswith("goal:") else os.path.join(ROOT, where), "rb").read()


def planted(submission):
    return {"kind": "proving-ground.verdict.v2", "submission": submission, "outcome": "accepted", "reason_code": "accepted", "message": judge.OK_LINE, "decided_by": "verdict job"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", allow_abbrev=False); m.add_argument("lie", choices=sorted(LIES)); m.add_argument("--goal", required=True); m.add_argument("--out", required=True)
    p = sub.add_parser("plant", allow_abbrev=False); p.add_argument("--out", required=True); p.add_argument("--submission", required=True)
    e = sub.add_parser("expect", allow_abbrev=False); e.add_argument("lie", choices=sorted(LIES)); e.add_argument("--verdict-dir", required=True)
    A = ap.parse_args()

    if A.cmd == "plant":
        os.makedirs(A.out, exist_ok=True)
        json.dump(planted(A.submission), open(os.path.join(A.out, "verdict.json"), "w", encoding="utf-8"), indent=1); sys.exit(0)

    if A.cmd == "make":
        goal = os.path.abspath(A.goal); answer = os.path.join(A.out, "answer"); os.makedirs(answer, exist_ok=True)
        raw = named_answer(A.lie, goal); rep = {"kind": "proving-ground.answer-report.v1", "answer_sha256": judge.sha(raw)}
        if A.lie == "forged-fault":
            rep.update(state="fault", reason_code="controls", message="the judge is not working on this machine")
        elif A.lie == "forged-export":
            # another problem's honest proof, built for real, handed over as the named answer's export
            other = judge.build_answer(goal, "and2_le_1", "proof", open(os.path.join(goal, "Proofs", "and2_le_1.lean"), "rb").read(), 300, answer, restore=True)
            assert other["state"] == "exported", other
            rep.update(state="exported", problem="xor2_le_4", answer_kind="proof", export_bytes=other["export_bytes"], seconds=other["seconds"])
        else:
            rep.update(judge.build_answer(goal, "xor2_le_4", "proof", raw, 300, answer, restore=True))
            assert rep["state"] == "exported", rep
        json.dump(rep, open(os.path.join(answer, "answer.json"), "w", encoding="utf-8"), indent=1)
        if A.lie == "overwrites-challenge":
            # a "challenge" in which the theorem is already proved: the answer's own export
            forged = os.path.join(A.out, "forged"); os.makedirs(forged, exist_ok=True)
            shutil.copy(os.path.join(answer, "solution.ndjson"), os.path.join(forged, "challenge.ndjson"))
        if os.environ.get("GITHUB_OUTPUT"): open(os.environ["GITHUB_OUTPUT"], "a").write("answer_sha256=%s\n" % rep["answer_sha256"])
        print(A.lie, "->", rep["state"], rep.get("reason_code", "")); sys.exit(0)

    # expect: what a consumer of verdicts would find
    _, vouched, outcome, code, kind = LIES[A.lie]
    vp, tp = os.path.join(A.verdict_dir, "verdict.json"), os.path.join(A.verdict_dir, "verdict.jwt")
    verdict = open(vp, "rb").read(); token = open(tp, encoding="ascii", errors="replace").read() if os.path.exists(tp) else ""
    import urllib.request
    keys = json.load(urllib.request.urlopen(KEYS, timeout=30))["keys"]
    env = os.environ
    why, claims = check(verdict, token, keys, env["GITHUB_REPOSITORY"], env["GITHUB_RUN_ID"], env["GITHUB_SHA"], env["GITHUB_RUN_ATTEMPT"], "lies.yml", env["GITHUB_EVENT_NAME"])
    v = json.loads(verdict)
    print("the token:", "vouches for the verdict" if why is None else "does NOT vouch for it: %s" % why)
    print("the verdict in the store says:", v.get("outcome"), v.get("reason_code"), v.get("fault_kind"), "|", v.get("message"))
    if why is not None and claims: print("claims:", json.dumps({k: claims.get(k) for k in ("repository", "run_id", "run_attempt", "sha", "workflow_sha", "event_name", "ref", "workflow_ref", "job_workflow_ref", "aud")}))
    if not vouched:
        ok = why is not None and "aud" in why
        sys.exit(0 if ok else "a verdict replaced after the verdict job ran must not be vouched for, and its token must name another verdict")
    got = (v.get("outcome"), v.get("reason_code"), v.get("fault_kind"))
    ok = why is None and got == (outcome, code, kind)
    sys.exit(0 if ok else "wanted a vouched-for verdict saying %s, and found %s%s" % ((outcome, code, kind), got, "" if why is None else ", not vouched for"))
