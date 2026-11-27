#!/usr/bin/env bash
# fetch_goal.sh
#
# Fetches the goal at exactly the commit the check names, into ./goal. The repository and the commit
# arrive as environment variables that inputs.sh has already matched against their patterns.
# Uses the network. Writes ./goal.
set -euo pipefail
git init -q goal
git -C goal fetch -q --depth 1 "https://github.com/${PG_GOAL_REPOSITORY}.git" "$PG_GOAL_COMMIT"
git -C goal checkout -q FETCH_HEAD
test "$(git -C goal rev-parse HEAD)" = "$PG_GOAL_COMMIT"
echo "the goal is at $PG_GOAL_COMMIT"
