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
| `verdict` | The two exports, and nothing to build | Runs Lean's own judge, [`lake comparator --paranoid`](https://lean-lang.org/doc/reference/latest/ValidatingProofs/), on the two exports. It replays the proof through six checkers | `verdict.json`, and `verdict.jwt`, a token that vouches for it |

Only the `answer` job runs submitted code, and nothing it says in the answer's favour is
believed. The `verdict` job runs none of the answer. It checks the challenge's export against the
hash the `challenge` job gave out, and that hash travels as a job output, not through the store
of files that a job which ran the answer could reach.

**Who vouches for the verdict.** Every job of a run can write the run's store of files, and
GitHub's record of a file does not say which job put it there. So a file named `verdict.json`
proves nothing about who wrote it. The `verdict` job alone is permitted to ask GitHub for an
identity token. It asks for one whose audience is the SHA-256 of `verdict.json`, and hands it on
as `verdict.jwt`. A consumer of verdicts checks that token before it believes the verdict:
its signature against GitHub's published keys, and the repository, run, attempt, workflow and
commit it names against the consumer's own record of what it started. `judge/verify_token.py`
does exactly that, with nothing but Python.

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

A verdict that is a fault says which of three kinds it is. `machine`: something no answer could
have caused, such as a challenge that would not build or a control that failed before the judge
ran. `answer_side`: it rests on the job that ran the answer, such as a control that failed after
the answer was built, or that job reporting a fault. `tampering`: something in the run wrote where
it should not, such as a challenge export that does not match its hash. Only the first kind is a
reason to think the checker itself is broken.

**An answer's build is bounded**, so that it cannot easily turn its own check into a fault. It
runs in a control group with a limit on memory and on processes. It is stopped when the disk runs
short, and when its export grows too large. One time budget covers the build and the export
together. Meeting a bound is a rejection, `resource_limit` or `timeout`.

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
| `resource_limit` | It used more memory, more processes, more disk or a larger export than a check allows | either |
| `runs_code` | The file would run code while it builds | The form screen, in `answer` |
| `too_large`, `not_utf8`, `hidden_characters` | The form screen refused the file | `answer` |

A reason from the `answer` job comes from a machine that ran the answer. It is believed because
it can only be a rejection.

`checkers_disagree` is still a rejection, and it deserves a person's attention: either the answer
leans on a fault in one checker, or a checker failed on a sound proof. It cannot be produced on
demand, so its reading is tested on the judge's own wording only.

## An answer is code

Lean lets a file run code while it is built: a command such as `#eval` can do whatever the person
building could do. The judge judges the proof and does not ask what else the file did. So a file
with an honest proof beside such a command would be accepted, and then committed to its goal's
repository, where it runs for everyone who builds the goal. The judge's sandbox protects only the
checker.

The form screen therefore refuses a file that would run code while it builds, with the reason
`runs_code`. The rule is lexical and reads the raw text, comments and strings included. It refuses:

- commands that run code or define syntax: `#eval`, `run_cmd`, `elab`, `macro`, `syntax`,
  `initialize`, `simproc` and their kin;
- the tactic `run_tac`;
- every attribute that is not on a short list an answer may use, such as `simp`, `instance` and
  `ext`. An attribute can install code, and a library can add such attributes faster than a list
  of bad ones could follow. An attribute list must also be readable to its end as plain words:
  Lean allows a comment or a string inside the brackets, and a `]` in one would hide what follows;
- names that reach the system or the elaborator: `IO`, `unsafe`, `MetaM`, `Lake` and their kin.

`judge/judge.py` has the lists.

**The screen is a speed bump, and for a goal with dependencies it is no more than that.** No list
is complete for Lean:

- `corpus/runs_code/macro.lean` reaches the file system through a macro without naming `IO` or
  `#eval` at all, which is why `macro` itself is refused.
- A plain function of Lean's own, named nothing like the system, writes a file from inside an
  elaborator.
- A library's tactics can take code as an option. `fixtures/mathlib-corpus/linarith_oracle.lean`
  hands an oracle of its own to Mathlib's `linarith`, which runs it while the file builds. The
  screen lets that file through, its proof is honest, and it is accepted. The corpus keeps it as a
  known gap, and shows on every run that it ran code with the screen on.

So the screen is one layer of three, and the other two are outside this repository: every build
of a goal runs in a sandbox that keeps nothing an answer's build wrote, and committed answers are
screened again when the rules change. For a goal with dependencies, the sandbox is what holds.

The judge must hold with the screen off. The corpus's files that attack the judge are run that way.

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

- `corpus/runs_code/` has one file for each of thirteen ways a file can run code while it builds.
  Each holds an honest proof, so the judge alone would accept it. Each must be refused by the
  screen, and each, built with the screen off, must leave a marker to show that it ran.
- `fills_disk.lean` and `eats_memory.lean` use up the disk and the memory. Each must be a
  rejection, `resource_limit`, and the control that runs after it must still pass.

The self-test judges every honest answer in the template, which must be accepted, and every corpus
file. It does the same for a one-problem goal that needs Mathlib, in `fixtures/`. It runs the
three steps on one machine, which tests the judging and not the separation of the jobs.

## When the answer job lies

The `lies` workflow is the test of the separation. The `answer` job is the one job that runs
submitted code, so nothing may rest on its word: code that escaped its sandbox, or a dependency's
build files, could make it say anything and write anything into the run's store. For each lie, a
real `challenge` job and a real `verdict` job run around a dishonest job in the answer's place,
and a last job plays the consumer of verdicts.

| The lie | How the run must end |
| --- | --- |
| None: an honest answer | Accepted, and the token vouches for the verdict |
| It reports the named answer as exported and hands over another proof's export | Rejected: the theorem is not in the export |
| It reports that the machine's controls failed | A fault of the kind `answer_side` |
| It replaces the challenge's export in the store | A fault of the kind `tampering`: the export does not match the hash the `challenge` job gave out |
| It puts an accepting verdict in the store before the `verdict` job runs | The real verdict replaces it, and the token vouches for the real one |
| It replaces the verdict in the store after the `verdict` job has run | The token does not vouch for what is in the store |

It tests the mechanism on a copy of `check.yml`'s wiring. `check.yml` itself has no switch that
makes its answer job lie, and should not have one. `judge/test_wiring.py` compares the copy with
the original where the test rests on it: which job may ask for a token, the steps that judge and
that ask for it, and how the files that matter are uploaded.

## Limits, stated plainly

- A goal that needs Mathlib has its dependencies and Mathlib's published build cache fetched
  before anything is judged. That step uses the network and runs outside the sandbox, so such a
  goal must describe its build in `lakefile.toml`, which is declarative, and not in
  `lakefile.lean`. The dependencies' own build files do run there, before the answer is fetched.
  So a goal's pinned dependencies are trusted as far as the goal itself is. The cache is
  downloaded afresh for every job; nothing is kept between checks.
- A goal's dependencies must be on the allow-list in `allowed-dependencies.json`, each package by
  its address and its revision, and that is checked before any `lake` command runs. Today the list
  holds Mathlib at one release and the packages that release pins.
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
python3 judge/test_classify.py       # how the judge's output is read
python3 judge/test_screen.py         # the screen for files that run code
python3 judge/test_verify_token.py   # the check of a verdict's token (needs openssl)
python3 judge/test_deps.py           # the check of a goal's dependencies
python3 judge/test_wiring.py         # the lying-job workflow still copies the real one (needs PyYAML)
```

You need Lean 4.36, Python 3.11 or later, and
[bubblewrap](https://github.com/containers/bubblewrap), which means Linux.

## Licence

MIT. Copyright (c) 2026 The Colony.
