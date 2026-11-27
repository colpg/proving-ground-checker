#!/usr/bin/env bash
# setup.sh <goal directory | Lean version>
#
# Installs the Lean release a goal names, taken only from the allow-list in lean-releases.json and
# compared by SHA-256, and the sandbox tool. Then makes sure the judge's sandbox can start, and
# records by which route in PG_SANDBOX_ROUTE:
#   native     the machine allows it as it comes
#   profile    an AppArmor profile for the one executable, bwrap
#   setting    the system-wide setting relaxed (the broad fix, used only if the narrow one fails)
#   untouched  PG_SKIP_SANDBOX_FIX=1 was set: nothing was tried (the self-test uses this)
# It also makes a control group with a limit on memory and on processes, and names it in PG_CGROUP.
# Meant for a GitHub-hosted machine that is thrown away. It uses sudo and changes the system.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
arg="${1:?a goal directory or a Lean version}"
if [ -f "$arg/lean-toolchain" ]; then spec="$(tr -d '[:space:]' < "$arg/lean-toolchain")"; else spec="$arg"; fi
version="${spec##*:}"; version="${version#v}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not a Lean release: $spec"; exit 2; }
want="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], {}).get("linux_x86_64_sha256", ""))' "$HERE/../lean-releases.json" "$version")"
[ -n "$want" ] || { echo "Lean $version is not on the allow-list (lean-releases.json)"; exit 2; }

tmp="${RUNNER_TEMP:-/tmp}"
curl -sSfL "https://github.com/leanprover/lean4/releases/download/v${version}/lean-${version}-linux.tar.zst" -o "$tmp/lean.tar.zst"
echo "${want}  $tmp/lean.tar.zst" | sha256sum -c -
# Outside the home directory: the judge's sandbox hides home directories.
sudo mkdir -p "/opt/lean-${version}"
sudo tar --zstd -xf "$tmp/lean.tar.zst" -C "/opt/lean-${version}" --strip-components=1
sudo apt-get update -qq
sudo apt-get install -y -qq bubblewrap
echo "/opt/lean-${version}/bin" >> "$GITHUB_PATH"

probe() { bwrap --unshare-user --ro-bind / / true 2>/dev/null; }
route=broken
if [ "${PG_SKIP_SANDBOX_FIX:-}" = "1" ]; then
  route=untouched
elif probe; then
  route=native
else
  printf 'abi <abi/4.0>,\ninclude <tunables/global>\nprofile bwrap /usr/bin/bwrap flags=(unconfined) {\n  userns,\n}\n' | sudo tee /etc/apparmor.d/bwrap > /dev/null
  sudo apparmor_parser -r /etc/apparmor.d/bwrap || true
  if probe; then
    route=profile
  else
    sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0 > /dev/null
    if probe; then route=setting; fi
  fi
fi
echo "Lean ${version} installed; sandbox route: ${route}"
echo "PG_SANDBOX_ROUTE=${route}" >> "$GITHUB_ENV"
[ "$route" != broken ] || { echo "the sandbox cannot start on this machine"; exit 1; }

# A control group for what is built and checked from an answer, so that an answer cannot take all
# of the machine's memory or fill its process table. judge.py puts each such command into it.
if [ "$route" != untouched ]; then
  cg=/sys/fs/cgroup/pg-answer
  sudo mkdir -p "$cg"
  echo "${PG_MEMORY_MAX:-10G}" | sudo tee "$cg/memory.max" > /dev/null
  echo "${PG_PIDS_MAX:-4096}" | sudo tee "$cg/pids.max" > /dev/null
  echo 0 | sudo tee "$cg/memory.swap.max" > /dev/null 2>&1 || true
  echo "control group ${cg}: memory $(cat "$cg/memory.max"), processes $(cat "$cg/pids.max")"
  echo "PG_CGROUP=${cg}" >> "$GITHUB_ENV"
fi
