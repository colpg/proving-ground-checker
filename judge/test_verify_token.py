"""Checks verify_token.py on tokens made here, with a key made here by `openssl`.

A real token can only come from a workflow run, and the `lies` workflow tests those. This file
tests the checking itself: a good token passes, and each thing that must stop a token does.
Run it with: python3 judge/test_verify_token.py   (needs the openssl command)"""
import base64, hashlib, json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_token import AUDIENCE, ISSUER, check  # noqa: E402

b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
tmp = tempfile.mkdtemp()


def new_key(kid):
    pem = os.path.join(tmp, kid + ".pem")
    subprocess.run(["openssl", "genrsa", "-out", pem, "2048"], check=True, capture_output=True)
    n = subprocess.run(["openssl", "rsa", "-in", pem, "-noout", "-modulus"], check=True, capture_output=True, text=True).stdout.strip().split("=")[1]
    return pem, {"kty": "RSA", "kid": kid, "alg": "RS256", "use": "sig", "n": b64(bytes.fromhex(n)), "e": "AQAB"}


def token(pem, kid, claims, alg="RS256"):
    signed = b64(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode()) + "." + b64(json.dumps(claims).encode())
    sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", pem], input=signed.encode(), check=True, capture_output=True).stdout
    return signed + "." + b64(sig)


pem, jwk = new_key("k1"); other_pem, other_jwk = new_key("k2")
VERDICT = b'{"outcome": "rejected"}\n'; REPO, RUN, SHA = "colpg/proving-ground-checker", "123", "a" * 40
GOOD = {"iss": ISSUER, "aud": AUDIENCE + hashlib.sha256(VERDICT).hexdigest(), "repository": REPO, "run_id": RUN, "run_attempt": "1", "sha": SHA,
        "workflow_sha": SHA, "event_name": "workflow_dispatch", "ref": "refs/tags/pin-1", "workflow_ref": REPO + "/.github/workflows/check.yml@refs/tags/pin-1",
        "runner_environment": "github-hosted"}
with_ = lambda **kw: dict(GOOD, **kw)
good = token(pem, "k1", GOOD)
CASES = [
    ("a good token", VERDICT, good, [jwk], True),
    ("the verdict was replaced after the token was made", b'{"outcome": "accepted"}\n', good, [jwk], False),
    ("a token for another verdict", VERDICT, token(pem, "k1", with_(aud=AUDIENCE + "0" * 64)), [jwk], False),
    ("a token with GitHub's default audience", VERDICT, token(pem, "k1", with_(aud="https://github.com/colpg")), [jwk], False),
    ("a token from another run", VERDICT, token(pem, "k1", with_(run_id="124")), [jwk], False),
    ("a token from a second attempt of the run", VERDICT, token(pem, "k1", with_(run_attempt="2")), [jwk], False),
    ("a token from another repository", VERDICT, token(pem, "k1", with_(repository="someone/else", workflow_ref="someone/else/.github/workflows/check.yml@refs/heads/main")), [jwk], False),
    ("a token from another workflow of the repository", VERDICT, token(pem, "k1", with_(workflow_ref=REPO + "/.github/workflows/selftest.yml@refs/heads/master")), [jwk], False),
    ("a token from another commit", VERDICT, token(pem, "k1", with_(sha="b" * 40, workflow_sha="b" * 40)), [jwk], False),
    ("a token whose workflow file is at another commit", VERDICT, token(pem, "k1", with_(workflow_sha="b" * 40)), [jwk], False),
    ("a token from a run started another way", VERDICT, token(pem, "k1", with_(event_name="pull_request")), [jwk], False),
    ("a token from a machine that is not GitHub's own", VERDICT, token(pem, "k1", with_(runner_environment="self-hosted")), [jwk], False),
    ("a token from another issuer", VERDICT, token(pem, "k1", with_(iss="https://example.org")), [jwk], False),
    ("a token signed by a key that is not GitHub's", VERDICT, token(other_pem, "k1", GOOD), [jwk], False),
    ("a token signed by a key GitHub does not list", VERDICT, token(other_pem, "k2", GOOD), [jwk], False),
    ("a token that says it needs no signature", VERDICT, good.rsplit(".", 1)[0].replace(b64(b'{"alg": "RS256", "kid": "k1", "typ": "JWT"}'), b64(b'{"alg": "none", "kid": "k1", "typ": "JWT"}')) + ".", [jwk], False),
    ("a token with its claims changed after signing", VERDICT, good.split(".")[0] + "." + b64(json.dumps(with_(run_id="999")).encode()) + "." + good.split(".")[2], [jwk], False),
    ("no token at all", VERDICT, "", [jwk], False),
    ("something that is not a token", VERDICT, "not.a.token", [jwk], False),
]

wrong = 0
for label, verdict, tok, keys, want in CASES:
    why, _ = check(verdict, tok, keys, REPO, RUN, SHA, ref="refs/tags/pin-1")
    good_ = (why is None) == want; wrong += not good_
    print("%-5s %-52s %s" % ("ok" if good_ else "WRONG", label, "vouched for" if why is None else why[:70]))
print("%d wrong" % wrong)
sys.exit(1 if wrong else 0)
