#!/usr/bin/env python3
"""verify_token.py --verdict FILE --token FILE --repository OWNER/NAME --run-id N --sha COMMIT
                [--run-attempt 1] [--workflow check.yml] [--event workflow_dispatch] [--ref REF] [--jwks FILE]

Checks that a verdict is vouched for by the job that made it. This is what a consumer of verdicts
has to do before it believes one, and The Colony's own check should do the same.

All the files of a workflow run sit in one store that every job of the run can write, so a file
named `verdict.json` proves nothing about who wrote it. The verdict job alone is permitted to ask
GitHub for an identity token, and it asks for one whose audience is the SHA-256 of the verdict.
This script checks, in order:

  - the token's signature, against GitHub's published keys (or the keys in --jwks);
  - its issuer, and that its audience is `proving-ground-verdict:sha256:<hash of the verdict file>`;
  - the repository, the run, the attempt, the workflow file, the commit and the event it names,
    against the values given here, which the caller takes from its own record of what it started;
  - that the job ran on one of GitHub's own machines. Whoever owns a self-hosted machine could
    have it ask for a token for any verdict.

GitHub changes its signing keys from time to time. A consumer that wants its record to stay
checkable should keep the key each token was checked against (its `kid`, `n` and `e`) beside it.

The token's expiry is not checked: the token is bound to one run and one verdict.

Reads two files, and GitHub's keys over the network unless --jwks is given. Changes nothing.
Exits 0 if the verdict is vouched for, 1 if not."""
import argparse, base64, hashlib, hmac, json, sys, urllib.request

ISSUER = "https://token.actions.githubusercontent.com"
KEYS = ISSUER + "/.well-known/jwks"
AUDIENCE = "proving-ground-verdict:sha256:"
SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")  # the DigestInfo header for SHA-256
unb64 = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def signed_by(token, keys):
    """True if the token carries an RS256 signature made by one of the keys. PKCS#1 v1.5, by hand,
    so that this needs nothing but Python."""
    head, body, sig = token.split(".")
    h = json.loads(unb64(head))
    if h.get("alg") != "RS256": return False
    key = next((k for k in keys if k.get("kid") == h.get("kid") and k.get("kty") == "RSA"), None)
    if key is None: return False
    n, e = int.from_bytes(unb64(key["n"]), "big"), int.from_bytes(unb64(key["e"]), "big")
    size = (n.bit_length() + 7) // 8
    if len(unb64(sig)) != size: return False
    got = pow(int.from_bytes(unb64(sig), "big"), e, n).to_bytes(size, "big")
    digest = hashlib.sha256((head + "." + body).encode("ascii")).digest()
    want = b"\x00\x01" + b"\xff" * (size - len(SHA256_PREFIX) - len(digest) - 3) + b"\x00" + SHA256_PREFIX + digest
    return hmac.compare_digest(got, want)


def check(verdict_bytes, token, keys, repository, run_id, sha, run_attempt="1", workflow="check.yml", event="workflow_dispatch", ref=None):
    """Returns (None, claims) if the verdict is vouched for, or (the reason it is not, claims)."""
    try:
        token = token.strip()
        if token.count(".") != 2: return "the token is not a signed token", {}
        claims = json.loads(unb64(token.split(".")[1]))
        if not signed_by(token, keys): return "the token's signature is not one of GitHub's", claims
    except (ValueError, KeyError, TypeError) as e:
        return "the token could not be read: %s" % type(e).__name__, {}
    want = {"iss": ISSUER, "aud": AUDIENCE + hashlib.sha256(verdict_bytes).hexdigest(), "repository": repository, "run_id": str(run_id),
            "run_attempt": str(run_attempt), "sha": sha, "workflow_sha": sha, "event_name": event, "runner_environment": "github-hosted"}
    if ref: want["ref"] = ref
    for name, value in want.items():
        if str(claims.get(name)) != value: return "the token's %s is %r, not %r" % (name, claims.get(name), value), claims
    if not str(claims.get("workflow_ref", "")).startswith("%s/.github/workflows/%s@" % (repository, workflow)):
        return "the token is from %r, not from %s" % (claims.get("workflow_ref"), workflow), claims
    return None, claims


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    for n in ("--verdict", "--token", "--repository", "--run-id", "--sha"): ap.add_argument(n, required=True)
    ap.add_argument("--run-attempt", default="1"); ap.add_argument("--workflow", default="check.yml")
    ap.add_argument("--event", default="workflow_dispatch"); ap.add_argument("--ref", default=None); ap.add_argument("--jwks", default=None)
    A = ap.parse_args()
    keys = json.load(open(A.jwks, encoding="utf-8")) if A.jwks else json.load(urllib.request.urlopen(KEYS, timeout=30))
    try: token = open(A.token, encoding="ascii").read()
    except (OSError, ValueError): token = ""
    why, claims = check(open(A.verdict, "rb").read(), token, keys["keys"], A.repository, A.run_id, A.sha, A.run_attempt, A.workflow, A.event, A.ref)
    if why: print("NOT vouched for:", why); sys.exit(1)
    print("vouched for: run %s attempt %s of %s at %s" % (claims["run_id"], claims["run_attempt"], claims["workflow_ref"], claims["sha"]))
