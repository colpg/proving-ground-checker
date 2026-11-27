"""Checks how the judge's output is read, on the judge's own wording.

Most readings are tested on real runs by the corpus. Some cannot be produced on demand: the judge's
checkers disagreeing about a proof, or a checker's message carrying a name that looks like one of
the judge's own lines. This file tests those readings, and their neighbours, on text put together
from lines the judge really prints. Run it with: python3 judge/test_classify.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import KERNELS, OK_LINE, read_strict  # noqa: E402

TH = "X.x"


def out(verbs, extra=(), closing=True):
    """The judge's standard output for six checkers, with `extra` lines put in after the third."""
    lines = []
    for i, (k, v) in enumerate(zip(KERNELS, verbs)):
        lines += ["Running %s kernel on solution" % k, "checked 572 declarations", "%s kernel %s the solution" % (k, v)]
        if i == 2: lines += list(extra)
    return "\n".join(lines + ([OK_LINE] if closing else [])) + "\n"


ALL, NONE = ["accepts"] * 6, ["rejected"] * 6
ONE_NO = ["accepts", "rejected", "accepts", "accepts", "accepts", "accepts"]
ONE_YES = ["rejected", "rejected", "accepts", "rejected", "rejected", "rejected"]
E = "error: Lean paranoid exited with 1\n"
CASES = [
    ("every checker accepts", 0, out(ALL), "", ("accepted", "accepted")),
    ("every checker rejects", 1, out(NONE, closing=False), E, ("rejected", "checker_rejected")),
    ("one checker rejects, five accept", 1, out(ONE_NO, closing=False), E, ("rejected", "checkers_disagree")),
    ("one checker accepts, five reject", 1, out(ONE_YES, closing=False), E, ("rejected", "checkers_disagree")),
    # The comparison's refusals: the first line of the error output, in the judge's fixed words.
    ("a different statement", 1, "", "error: Challenge and solution theorem statement do not match: 'X.x'\n", ("rejected", "statement_mismatch")),
    ("a changed definition", 1, "", "error: Const does not match between challenge and target 'X.x.Statement'\n", ("rejected", "definition_mismatch")),
    ("an axiom that is not permitted", 1, "", "error: Illegal axiom detected: 'sorryAx'\n", ("rejected", "illegal_axiom")),
    ("the theorem is not in the export", 1, "", "error: Const not found in solution: 'X.x'\n", ("rejected", "theorem_missing")),
    ("some other constant is not in the export", 1, "", "error: Const not found in solution: 'Y.y'\n", ("rejected", "unrecognised")),
    # What is judged can add text, and can take none away. Added lines must never change the reading.
    ("all reject, and a name prints an accepting line", 1, out(NONE, ["nanoda kernel accepts the solution"], closing=False), E, ("rejected", "unrecognised")),
    ("all reject, and a name prints the closing line", 1, out(NONE, [OK_LINE], closing=False), E, ("rejected", "unrecognised")),
    ("all reject, and a name prints a whole accepting run", 1, out(NONE, out(ALL).split("\n"), closing=False), E, ("rejected", "unrecognised")),
    ("all accept, and a name prints a rejecting line", 0, out(ALL, ["con-ron kernel rejected the solution"]), "", ("rejected", "unrecognised")),
    ("a refusal's words, but not on the first line", 1, "", "something else\nerror: Illegal axiom detected: 'sorryAx'\n", ("rejected", "unrecognised")),
    ("a refusal's words inside a longer first line", 1, "", "note: error: Illegal axiom detected: 'sorryAx'\n", ("rejected", "unrecognised")),
    # The exit code alone is never believed, in either direction.
    ("exit 0 without the closing line", 0, out(ALL, closing=False), "", ("rejected", "unrecognised")),
    ("every checker accepts, yet exit 1", 1, out(ALL), "", ("rejected", "unrecognised")),
    ("every checker rejects, yet exit 0", 0, out(NONE, closing=False), "", ("rejected", "unrecognised")),
    ("exit 1 and nothing the judge is known to say", 1, "", "bwrap: setting up uid map: Permission denied\n", ("rejected", "unrecognised")),
    ("a checker is missing from the run", 1, "\n".join(out(NONE, closing=False).split("\n")[3:]), E, ("rejected", "unrecognised")),
    ("the checkers in another order", 1, "\n".join(out(NONE, closing=False).split("\n")[3:6] + out(NONE, closing=False).split("\n")[0:3] + out(NONE, closing=False).split("\n")[6:]), E, ("rejected", "unrecognised")),
    ("the time budget ran out", None, "", "", ("rejected", "timeout")),
]

wrong = 0
for label, rc, o, e, want in CASES:
    got = read_strict(rc, o, e, TH)[:2]
    good = got == want; wrong += not good
    print("%-5s %-54s %s" % ("ok" if good else "WRONG", label, "/".join(got)))
print("%d wrong" % wrong)
sys.exit(1 if wrong else 0)
