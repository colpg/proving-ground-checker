"""Checks how the judge's output is read, on the judge's own wording.

Most readings are tested on real runs by the corpus. One cannot be produced on demand: the judge's
checkers disagreeing about a proof. This file tests that reading, and its neighbours, on text put
together from lines the judge really prints. Run it with: python3 judge/test_classify.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import OK_LINE, classify  # noqa: E402

KERNELS = ["Lean paranoid", "lean4lean", "nanoda", "con-leche", "con-ron", "Lean default"]
HEAD = ["Building Problems.x", "Build completed successfully (9 jobs).", "Building Proofs.x", "Build completed successfully (9 jobs)."]


def text(verbs, tail=()):
    lines = list(HEAD)
    for k, v in zip(KERNELS, verbs):
        lines += ["Running %s kernel on solution" % k, "%s kernel %s the solution" % (k, v)]
    return "\n".join(lines + list(tail)) + "\n"


def read(rc, out):
    return classify(rc, out, "Problems.x", "Proofs.x", "X.x")[:2]


CASES = [
    ("every checker accepts", 0, text(["accepts"] * 6, [OK_LINE]), ("accepted", "accepted")),
    ("every checker rejects", 1, text(["rejected"] * 6, ["error: Lean paranoid exited with 1"]), ("rejected", "checker_rejected")),
    ("one checker rejects, five accept", 1, text(["accepts", "rejected", "accepts", "accepts", "accepts", "accepts"]), ("rejected", "checkers_disagree")),
    ("one checker accepts, five reject", 1, text(["rejected", "rejected", "accepts", "rejected", "rejected", "rejected"]), ("rejected", "checkers_disagree")),
    # The exit code alone is never believed, in either direction.
    ("exit 0 without the closing line", 0, text(["accepts"] * 6), ("fault", None)),
    ("exit 1 with nothing the judge is known to say", 1, "bwrap: setting up uid map: Permission denied\n", ("fault", None)),
    ("every checker accepts, yet exit 1", 1, text(["accepts"] * 6), ("fault", None)),
]

wrong = 0
for label, rc, out, want in CASES:
    got = read(rc, out)
    good = got[0] == want[0] and (want[1] is None or got[1] == want[1]); wrong += not good
    print("%-5s %-48s %s" % ("ok" if good else "WRONG", label, "/".join(got)))
print("%d wrong" % wrong)
sys.exit(1 if wrong else 0)
