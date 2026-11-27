#!/usr/bin/env bash
# deps.sh <goal directory>
#
# Brings a goal's dependencies, and Mathlib's published build cache, onto the machine before the
# judge runs. A goal with no dependencies needs nothing.
#
# A goal with dependencies must describe its build in lakefile.toml, which is declarative. A
# lakefile.lean is code, and it would run here, outside the judge's sandbox.
#
# The dependencies' own build files do run here. So every package the goal pins must be on the
# allow-list in allowed-dependencies.json, by address and by revision, and that is checked first.
#
# Uses the network. Writes inside the goal directory only.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
goal="${1:?a goal directory}"
[ -f "$goal/lake-manifest.json" ] || { echo "the goal has no lake-manifest.json"; exit 2; }
# Before any `lake` command: every dependency must be on the allow-list, at a revision it names.
python3 "$HERE/deps_check.py" "$goal"
n="$(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1])).get("packages", [])))' "$goal/lake-manifest.json")"
if [ "$n" = "0" ]; then echo "the goal has no dependencies"; exit 0; fi
[ ! -e "$goal/lakefile.lean" ] || { echo "a goal with dependencies must use lakefile.toml, not lakefile.lean"; exit 2; }
[ -f "$goal/lakefile.toml" ] || { echo "the goal has no lakefile.toml"; exit 2; }
cd "$goal"
if python3 -c 'import json, sys; sys.exit(0 if any(p.get("name") == "mathlib" for p in json.load(open("lake-manifest.json")).get("packages", [])) else 1)'; then
  timeout 1500 lake exe cache get
else
  echo "Mathlib is not among the dependencies: they will be built inside the sandbox"
fi
du -sh .lake 2> /dev/null || true
