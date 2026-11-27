A one-problem goal that needs Mathlib, used only by this repository's self-test.

It commits its `lake-manifest.json`, as a real goal does. Every package in it is on the allow-list in `allowed-dependencies.json`, and the self-test checks that before any `lake` command runs.
