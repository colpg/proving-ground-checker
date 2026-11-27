"""Checks that lie-run.yml still copies check.yml where it matters.

The `lies` workflow tests what a check does when its answer job lies, on a copy of check.yml's
challenge and verdict jobs. If the copy drifted, that test would pass while the real workflow had
changed. This compares the parts the test rests on: which job may ask for an identity token, where
the verdict job takes the challenge's hash from, the steps that judge and that ask for the token,
and how the files that matter are uploaded.
Run it with: python3 judge/test_wiring.py   (needs PyYAML)"""
import os, sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load = lambda name: yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8"))
check, lie = load("check.yml"), load("lie-run.yml")
SUFFIX = "-${{ inputs.lie }}"
wrong = 0


def same(label, a, b):
    global wrong
    good = a == b and a is not None; wrong += not good
    print("%-5s %s" % ("ok" if good else "WRONG", label))
    if not good: print("      check.yml:   %r\n      lie-run.yml: %r" % (a, b))


def step(job, starts=None, uses=None, name=None):
    """One step of a job: by how its name starts, or by the action it uses and the file it names."""
    for s in job["steps"]:
        if starts and str(s.get("name", "")).startswith(starts): return s
        if uses and str(s.get("uses", "")).startswith(uses) and str(s.get("with", {}).get("name", "")).replace(SUFFIX, "") == name: return s
    return {}


def may_ask(workflow):
    """The jobs of a workflow that are permitted to ask GitHub for an identity token."""
    top = (workflow.get("permissions") or {}).get("id-token") == "write"
    return sorted(n for n, j in workflow["jobs"].items() if (j.get("permissions") or {}).get("id-token", "write" if top and "permissions" not in j else None) == "write")


cv, lv = check["jobs"]["verdict"], lie["jobs"]["verdict"]
same("only the verdict job may ask for an identity token, in both", may_ask(check), may_ask(lie))
same("  and that is the verdict job alone", may_ask(check), ["verdict"])
same("the verdict job's permissions", cv.get("permissions"), lv.get("permissions"))
# The fingerprint, the plan and the toolchain must reach the verdict job as the challenge job's
# outputs, and not through the store of files: the check for a replaced challenge export rests on it.
FROM_OUTPUTS = {"FINGERPRINT": "${{ needs.challenge.outputs.fingerprint }}", "PLAN": "${{ needs.challenge.outputs.plan }}", "TOOLCHAIN": "${{ needs.challenge.outputs.toolchain }}"}
taken = lambda job: {k: (job.get("env") or {}).get(k) for k in FROM_OUTPUTS}
same("where the verdict job takes the fingerprint, the plan and the toolchain from", taken(cv), taken(lv))
same("  and that is the challenge job's outputs", taken(cv), FROM_OUTPUTS)
same("the outputs the challenge job gives", check["jobs"]["challenge"].get("outputs"), lie["jobs"]["challenge"].get("outputs"))
same("the step that judges the two exports", step(cv, "Run the controls, judge").get("run"), step(lv, "Run the controls, judge").get("run"))
same("the step that asks for the token", step(cv, "Ask GitHub for a token").get("run"), step(lv, "Ask GitHub for a token").get("run"))
up = lambda job, name: {k: v for k, v in step(job, uses="actions/upload-artifact@", name=name).get("with", {}).items() if k in ("path", "overwrite", "if-no-files-found")}
same("how the verdict and its token are uploaded", up(cv, "verdict"), up(lv, "verdict"))
same("  and that upload replaces what is there", up(cv, "verdict").get("overwrite"), True)
same("how the challenge's export is uploaded", up(check["jobs"]["challenge"], "challenge"), up(lie["jobs"]["challenge"], "challenge"))
same("  and that upload replaces what is there", up(check["jobs"]["challenge"], "challenge").get("overwrite"), True)
same("the step that builds and exports the challenge", step(check["jobs"]["challenge"], "Build the challenge").get("run"), step(lie["jobs"]["challenge"], "Build the challenge").get("run"))
act = lambda job, name: step(job, uses="actions/upload-artifact@", name=name).get("uses")
same("the action that uploads the verdict, by its commit", act(cv, "verdict"), act(lv, "verdict"))
print("%d wrong" % wrong)
sys.exit(1 if wrong else 0)
