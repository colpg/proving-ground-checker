"""Checks deps_check.py on small goals made here: one it must pass, and one for each thing it must
refuse. Run it with: python3 judge/test_deps.py"""
import json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deps_check import check  # noqa: E402

A, B = "https://github.com/example/alpha", "https://github.com/example/beta"
tmp = tempfile.mkdtemp(); allow = os.path.join(tmp, "allow.json")
json.dump({"packages": {A: ["a" * 40], B + ".git": ["b" * 40, "c" * 40]}}, open(allow, "w"))
pkg = lambda name, url, rev, **kw: dict({"name": name, "type": "git", "url": url, "rev": rev, "subDir": None, "inputRev": "v1"}, **kw)
LAKE = 'name = "g"\n\n[[require]]\nname = "alpha"\ngit = "%s"\nrev = "v1"\n' % A
n = 0


def goal(packages, lakefile=LAKE, lean=False):
    global n
    n += 1; d = os.path.join(tmp, "g%d" % n); os.makedirs(d)
    json.dump({"version": "1.3.0", "packages": packages}, open(os.path.join(d, "lake-manifest.json"), "w"))
    open(os.path.join(d, "lakefile.toml"), "w").write(lakefile)
    if lean: open(os.path.join(d, "lakefile.lean"), "w").write("-- code\n")
    return d


GOOD = [pkg("alpha", A, "a" * 40), pkg("beta", B, "c" * 40)]
CASES = [
    ("every package on the list, at a listed revision", goal(GOOD), True),
    ("no dependencies at all", goal([], 'name = "g"\n'), True),
    ("an address written another way", goal([pkg("alpha", A.upper().replace("HTTPS", "https") + ".git/", "a" * 40)]), True),
    ("a package from somewhere else", goal(GOOD + [pkg("gamma", "https://github.com/someone/else", "a" * 40)]), False),
    ("a listed package at an unlisted revision", goal([pkg("alpha", A, "d" * 40)]), False),
    ("a revision that is a branch name", goal([pkg("alpha", A, "main")]), False),
    ("a package that is a path on the machine", goal([pkg("alpha", A, "a" * 40, type="path")]), False),
    ("a package from a sub-directory", goal([pkg("alpha", A, "a" * 40, subDir="evil")]), False),
    ("a require the manifest does not pin", goal(GOOD, LAKE + '\n[[require]]\nname = "surprise"\ngit = "https://github.com/someone/else"\n'), False),
    ("a require that names another address", goal(GOOD, 'name = "g"\n\n[[require]]\nname = "alpha"\ngit = "https://github.com/someone/else"\n'), False),
    ("a require at another revision", goal(GOOD, 'name = "g"\n\n[[require]]\nname = "alpha"\nrev = "v2"\n'), False),
    ("a require from a path", goal(GOOD, 'name = "g"\n\n[[require]]\nname = "alpha"\npath = "../x"\n'), False),
    ("a lakefile.lean beside the lakefile.toml", goal(GOOD, lean=True), False),
]

wrong = 0
for label, d, want in CASES:
    bad = check(d, allow); good = (not bad) == want; wrong += not good
    print("%-5s %-50s %s" % ("ok" if good else "WRONG", label, "passed" if not bad else bad[0][:80]))
print("%d wrong" % wrong)
sys.exit(1 if wrong else 0)
