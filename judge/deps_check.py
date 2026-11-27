#!/usr/bin/env python3
"""deps_check.py <goal directory> [allow-list file]

Checks a goal's dependencies against the allow-list, before any `lake` command runs on the goal.

A dependency's own build files run on the checker's machines outside the sandbox, so naming a
dependency is a decision about trust. This check refuses a goal unless:

  - every package in lake-manifest.json is a git package, with no sub-directory, whose address is
    on the allow-list and whose revision is one the list names for that address;
  - every `require` in lakefile.toml names a package that the manifest holds, and agrees with it,
    so that Lake has no reason to fetch anything the manifest does not pin;
  - the goal has no lakefile.lean, which is code and would run here.

A goal with no dependencies passes. Reads two or three files. Changes nothing. Exits 0 or 2."""
import json, os, re, sys, tomllib

HERE = os.path.dirname(os.path.abspath(__file__))


def address(url):
    """An address in one form: lower-case host and path, no trailing slash, no .git."""
    u = url.strip().rstrip("/")
    return (u[:-4] if u.endswith(".git") else u).lower()


def check(goal, allow_file):
    allowed = {address(u): set(revs) for u, revs in json.load(open(allow_file, encoding="utf-8"))["packages"].items()}
    if os.path.exists(os.path.join(goal, "lakefile.lean")): return ["the goal has a lakefile.lean, which is code; a goal describes its build in lakefile.toml"]
    try: manifest = json.load(open(os.path.join(goal, "lake-manifest.json"), encoding="utf-8"))
    except (OSError, ValueError) as e: return ["the goal's lake-manifest.json could not be read: %s" % e]
    try: lakefile = tomllib.load(open(os.path.join(goal, "lakefile.toml"), "rb"))
    except (OSError, tomllib.TOMLDecodeError) as e: return ["the goal's lakefile.toml could not be read: %s" % e]
    bad, held = [], {}
    for p in manifest.get("packages", []):
        name = p.get("name"); held[name] = p
        if p.get("type") != "git": bad.append("package %r is not a git package" % name); continue
        if p.get("subDir"): bad.append("package %r is taken from a sub-directory" % name)
        url, rev = address(str(p.get("url", ""))), str(p.get("rev", ""))
        if url not in allowed: bad.append("package %r comes from %s, which is not on the allow-list" % (name, p.get("url")))
        elif not re.fullmatch(r"[0-9a-f]{40}", rev) or rev not in allowed[url]: bad.append("package %r is at %s, which the allow-list does not name for %s" % (name, rev, p.get("url")))
    for r in lakefile.get("require", []):
        name = r.get("name"); p = held.get(name)
        if p is None: bad.append("lakefile.toml requires %r, which lake-manifest.json does not pin" % name); continue
        if "path" in r: bad.append("lakefile.toml takes %r from a path" % name)
        if "git" in r and address(str(r["git"])) != address(str(p.get("url", ""))): bad.append("lakefile.toml and lake-manifest.json disagree about where %r comes from" % name)
        want = r.get("rev")
        if want is not None and want not in (p.get("rev"), p.get("inputRev")): bad.append("lakefile.toml asks for %r at %s, and lake-manifest.json pins something else" % (name, want))
    return bad


if __name__ == "__main__":
    goal = sys.argv[1]; allow = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(HERE), "allowed-dependencies.json")
    bad = check(goal, allow)
    for b in bad: print("refused:", b)
    if bad: sys.exit(2)
    print("every dependency of the goal is on the allow-list")
