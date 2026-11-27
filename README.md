# Proving Ground checker

The judge of Proving Ground: a workflow that takes one answer to one problem and says whether it
is accepted, on GitHub-hosted machines that are thrown away afterwards.

Proving Ground is a part of [The Colony](https://thecolony.ai) that is still being designed. It
does not exist as a service yet, and nothing starts this workflow in production. What works today
is the judge itself and its self-test, which runs on every push.

## What it does

A **goal** is a public Lean 4 repository laid out like the
[goal template](https://github.com/colpg/proving-ground-goal-template). Each **problem** is
one formal statement, named in the goal's library. An **answer** is a Lean file: a proof, a
refutation, or the implication of a cut.

The `check` workflow is given a goal, a commit, a problem, the address and hash of an answer, and
a time budget. It runs three jobs on three machines.

| Job | Is given | Does | Hands on |
| --- | --- | --- | --- |
| `challenge` | The goal. Never the answer | Writes the challenge from the names in the goal's manifests, builds it, and exports it with Lean's own exporter | The export, and its SHA-256 as a job output |
| `answer` | The goal and the answer | Builds the answer inside a sandbox with no network, within the time budget, and exports it | The export, or the reason there is none |
| `verdict` | The two exports, and nothing to build | Runs Lean's own judge, [`lake comparator --paranoid`](https://lean-lang.org/doc/reference/latest/ValidatingProofs/), on the two exports. It replays the proof through six checkers | `verdict.json` |

Only the `answer` job runs submitted code, and nothing it says in the answer's favour is
believed. The `verdict` job runs none of the answer. It checks the challenge's export against the
hash the `challenge` job gave out, and that hash travels as a job output, not through the store
of files that a job which ran the answer could reach.

The SHA-256 of a challenge's export is the problem's **fingerprint**. The export holds the
statement and every definition it reaches, so the fingerprint changes when anything the statement
means changes.

Before it uses them, every job matches every input against a pattern, and no input is ever put
into a command. Each job installs the Lean release the goal names only if it is on the allow-list
in `lean-releases.json`, and compares its SHA-256. No job holds a secret, the token can only read
this repository, and every action is pinned by its full commit hash.

## The three findings

| Finding | Requires |
| --- | --- |
| `accepted` | In the `verdict` job: every control behaved, the judge exited with 0, and its output held exactly its own lines, ending with its closing line |
| `rejected` | Every control behaved, and the answer was not accepted |
| `fault` | A control misbehaved, or something the answer never touched could not be fetched or built. A fault says nothing about the answer |

**A fault is about the machine, never the answer.** A pair of the checker's own files that must
be accepted is judged before the answer is touched and again after it. If both pass, the machine
was working, and whatever happened in between belongs to the answer. So an answer that never
finishes, or that the checker cannot read, is a rejection.

**The exit code alone is never believed.** On Ubuntu 24.04 as it comes, the judge's sandbox
cannot start, and the judge then exits with 1, the same code as a rejection. The self-test has a
job that checks this case reads as a fault.

**What is judged can add text to the judge's output, and can take none away.** Names in an export
can reach the screen through a checker's own messages. So a reading is believed only when each of
the judge's own lines appears exactly once and in the judge's order, and a refusal by comparison
is read only from the first line of the judge's error output. Anything else is `unrecognised`.

Reasons for a rejection:

| Reason | Means | Decided by |
| --- | --- | --- |
| `statement_mismatch` | The answer proves a different statement under the problem's name | `verdict` |
| `definition_mismatch` | The answer changed a definition the statement reaches | `verdict` |
| `illegal_axiom` | It uses an axiom outside the permitted list. `sorry` is one | `verdict` |
| `checker_rejected` | It built, and every checker then refused the proof | `verdict` |
| `checkers_disagree` | It built, and some checkers refused the proof while others accepted it | `verdict` |
| `unrecognised` | The judge's output could not be read as any of the above | `verdict` |
| `build_failed` | The answer does not build | `answer` |
| `theorem_missing` | It does not declare the theorem | `answer`, `verdict`, or the form screen |
| `export_failed` | It built, and what it built could not be exported | `answer` |
| `timeout` | It did not finish inside the time budget, building or being checked | either |
| `too_large`, `not_utf8`, `hidden_characters` | The form screen refused the file | `answer` |

A reason from the `answer` job comes from a machine that ran the answer. It is believed because
it can only be a rejection.

`checkers_disagree` is still a rejection, and it deserves a person's attention: either the answer
leans on a fault in one checker, or a checker failed on a sound proof. It cannot be produced on
demand, so its reading is tested on the judge's own wording only.

## The corpus

`corpus/` holds answers to the template's problems, each with the finding it must draw.
`corpus/corpus.json` lists them. Most are dishonest: a proof that is `sorry`, a statement declared
as its own axiom, a true proof of a weaker statement, a statement redefined as something trivial,
a proof by native evaluation, a theorem added with Lean's own check switched off, a cut whose
implication is `sorry`. Some attack the checker and not the mathematics:

- `prints_judge_wording.lean` prints every line the judge prints for an accepted answer, around a
  bogus proof. Its text must change nothing.
- `honest_but_loud.lean` is an honest proof that prints the judge's refusals. It must be accepted.
- `never_finishes.lean` never finishes building. It must be a rejection, not a fault.
- `writes_into_build.lean` replaces a compiled file of the goal's library while it builds.
- `sandbox_probe.lean` is an honest proof that refuses to build unless it finds itself in the
  sandbox. If the sandbox were ever loosened, it would stop being accepted.

The self-test judges every honest answer in the template, which must be accepted, and every corpus
file. It does the same for a one-problem goal that needs Mathlib, in `fixtures/`. It runs the
three steps on one machine, which tests the judging and not the separation of the jobs.

## Limits, stated plainly

- A goal that needs Mathlib has its dependencies and Mathlib's published build cache fetched
  before anything is judged. That step uses the network and runs outside the sandbox, so such a
  goal must describe its build in `lakefile.toml`, which is declarative, and not in
  `lakefile.lean`. The dependencies' own build files do run there, before the answer is fetched.
  So a goal's pinned dependencies are trusted as far as the goal itself is. The cache is
  downloaded afresh for every job; nothing is kept between checks.
- The fingerprint is stricter than it needs to be. It also changes with the Lean release, with a
  dependency, and with a proof inside a definition the statement reaches.
- The `answer` job's sandbox is this repository's own call to `bwrap`, with the arguments Lean's
  judge uses. It protects the machine and the network. The finding does not rest on it.
- A verdict records who started its run. Anyone with write access can start this workflow by
  hand, or run it again, so a consumer of verdicts should believe only runs its own app started,
  and only their first attempt.
- The certificate judge, for problems settled by a certificate and not a Lean file, is not built.
- An accepted finding means the statement was proved as stated. Whether a statement says what its
  source says is not something a machine can judge.
- The judge rests on Lean's logic and on at least one of its checkers being correct. Two of the
  six are Lean's own kernel, in two builds.

## Run it yourself

```
python3 judge/judge.py controls
python3 judge/judge.py corpus --goal <a checkout of the goal template> --corpus corpus/corpus.json
python3 judge/test_classify.py
```

You need Lean 4.36, Python 3.11 or later, and
[bubblewrap](https://github.com/containers/bubblewrap), which means Linux.

## Licence

MIT. Copyright (c) 2026 The Colony.
