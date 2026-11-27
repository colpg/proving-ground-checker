#!/usr/bin/env bash
# inputs.sh
#
# Matches every input of the check workflow against its pattern. The inputs arrive as environment
# variables and are never put into a command. Every job runs this before it uses any of them.
# Reads the environment and one file of this repository. Changes nothing.
set -euo pipefail
[[ "${SUBMISSION:-}" =~ ^[A-Za-z0-9_-]{1,64}$ ]] || { echo "submission"; exit 2; }
[[ "${PG_GOAL_REPOSITORY:-}" =~ ^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$ ]] || { echo "goal_repository"; exit 2; }
[[ "${PG_GOAL_COMMIT:-}" =~ ^[0-9a-f]{40}$ ]] || { echo "goal_commit"; exit 2; }
[[ "${PROBLEM:-}" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || { echo "problem"; exit 2; }
[[ "${ANSWER_KIND:-}" =~ ^(proof|refutation|cut)$ ]] || { echo "answer_kind"; exit 2; }
[[ "${ANSWER_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || { echo "answer_sha256"; exit 2; }
[[ "${BUDGET:-}" =~ ^[1-9][0-9]{1,3}$ ]] || { echo "budget_seconds"; exit 2; }
[ "$BUDGET" -ge 60 ] && [ "$BUDGET" -le 1500 ] || { echo "budget_seconds"; exit 2; }
HOSTS="$(cd "$(dirname "$0")/.." && pwd)/allowed-answer-hosts.txt" python3 -c '
import os, sys, urllib.parse
u = urllib.parse.urlsplit(os.environ.get("ANSWER_URL", ""))
hosts = [l.strip() for l in open(os.environ["HOSTS"]) if l.strip() and not l.startswith("#")]
ok = u.scheme == "https" and u.hostname in hosts and not u.username and u.port in (None, 443) and len(os.environ.get("ANSWER_URL", "")) <= 500
sys.exit(0 if ok else "answer_url is not an https address on an allowed host")
'
echo "every input matches its pattern"
