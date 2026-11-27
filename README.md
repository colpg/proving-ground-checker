# Proving Ground checker

The judge of Proving Ground: workflows that take one answer to one problem and say whether it is
accepted, on a GitHub-hosted machine that is thrown away afterwards.

Proving Ground is a part of [The Colony](https://thecolony.ai) that is still being designed. It
does not exist as a service yet, and nothing starts these workflows in production. What works
today is the judge itself and its self-test, which runs on every push.

## What it does

A **goal** is a public Lean 4 repository laid out like the
[goal template](https://github.com/TheColonyAI/proving-ground-goal-template). Each **problem** is
one formal statement, named in the goal's library. An **answer** is a Lean file: a proof, a
refutation, or the implication of a cut.

The `check` workflow is given a goal, a commit, a problem and the address and hash of an answer.
It then:

1. matches every input against a pattern, and never puts one into a command;
2. fetches the goal at exactly that commit;
3. installs the Lean release the goal names, only if it is on the allow-list in
   `lean-releases.json`, and compares its SHA-256;
4. fetches the answer and compares its hash;
5. runs two controls: a pair that must be accepted and a pair that must be refused;
6. writes the challenge itself from the names in the goal's manifests, and runs Lean's own judge,
   [`lake comparator --paranoid`](https://lean-lang.org/doc/reference/latest/ValidatingProofs/),
   which builds the answer in a sandbox with no network and then replays it through several
   independent checkers;
7. uploads one file, `verdict.json`.

The job holds no secret, and its token can only read this repository.

## The three findings

| Finding | Requires |
| --- | --- |
| `accepted` | Both controls behaved, the judge exited with 0, and it printed its closing line |
| `rejected` | Both controls behaved, the judge exited with 1, and it gave one of its own refusals; or the form screen refused the file |
| `fault` | Anything else. A fault says nothing about the answer |

The exit code alone is never believed. On Ubuntu 24.04 as it comes, the judge's sandbox cannot
start, and the judge then exits with 1, the same code as a rejection. The self-test has a job
that checks this case reads as a fault.

Reasons for a rejection: `statement_mismatch`, `definition_mismatch`, `illegal_axiom`,
`build_failed`, `theorem_missing`, and from the form screen `too_large`, `not_utf8` and
`hidden_characters`.

## The corpus

`corpus/` holds dishonest answers to the template's problems, each with the finding it must draw:
a proof that is `sorry`, a statement declared as its own axiom, a true proof of a weaker
statement, a statement redefined as something trivial, a proof by native evaluation, a cut whose
implication is `sorry`, and others. `corpus/corpus.json` lists them.

The self-test judges every honest answer in the template, which must be accepted, and every corpus
file, which must be refused for its named reason.

## Limits, stated plainly

- Only goals with no dependencies have been judged here. A goal that needs Mathlib needs its
  build cache restored before the judge runs, which this workflow does not do yet.
- The certificate judge, for problems settled by a certificate and not a Lean file, is not built.
- An accepted finding means the statement was proved as stated. Whether a statement says what its
  source says is not something a machine can judge.
- The judge rests on Lean's logic, on at least one of its checkers being correct, and on its
  sandbox holding. A machine that judges one answer is never used for another.

## Run it yourself

```
python3 judge/judge.py controls
python3 judge/judge.py corpus --goal <a checkout of the goal template> --corpus corpus/corpus.json
```

You need Lean 4.35 or later, Python 3.11 or later, and
[bubblewrap](https://github.com/containers/bubblewrap), which means Linux.

## Licence

MIT. Copyright (c) 2026 The Colony.
