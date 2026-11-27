A one-problem goal that needs Mathlib, used only by this repository's self-test.

It carries no `lake-manifest.json`: the self-test resolves Mathlib at the tag in `lakefile.toml` when it runs. A real goal commits its manifest.
