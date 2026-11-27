"""Checks the part of the form screen that refuses a file which would run code while it builds.

The corpus shows that each refused construct really runs code. This file tests the rule itself, on
small pieces of text: what it must refuse, the ways of writing a refused thing that must not slip
past, and the honest text it must leave alone. Run it with: python3 judge/test_screen.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import runs_code  # noqa: E402

REFUSED = [
    '#eval 1 + 1', '#eval! foo', 'run_cmd pure ()', 'run_elab pure ()', 'run_meta pure ()',
    'initialize x : Nat ← pure 1', 'builtin_initialize pure ()',
    'elab "x" : command => pure ()', 'elab_rules : command | `(x) => pure ()',
    'macro "x" : term => `(1)', 'macro_rules | `(x) => `(1)', 'syntax "x" : term', 'declare_syntax_cat c',
    'simproc s (_ + _) := fun _ => return .continue', 'dsimproc s (_ + _) := fun _ => return .continue',
    'simproc_decl s (_ + _) := fun _ => return .continue', 'builtin_simproc s (_) := x',
    'example : True := by run_tac pure ()', 'example : True := by_elab pure ()',
    '@[term_elab x] def f := 1', '@[command_elab x] def f := 1', '@[tactic x] def f := 1',
    '@[implemented_by g] def f := 1', '@[extern "c_f"] def f : Nat := 1', '@[init] def f := 1',
    '@[builtin_term_elab x] def f := 1', '@[macro x] def f := 1', '@[app_delab x] def f := 1', '@[export c_f] def f := 1',
    'def f : IO Unit := pure ()', 'def f : EIO Nat Unit := pure ()', 'def f : BaseIO Unit := pure ()',
    'def f := unsafeIO x', 'def f := unsafeBaseIO x', 'unsafe def f := 1',
    'def f : MetaM Unit := pure ()', 'def f : TacticM Unit := pure ()', 'def f : CommandElabM Unit := pure ()',
    # ways of writing a refused thing that must not slip past
    'def f := _root_.IO.println "x"', 'def f := Lean.IO.x', 'local macro "x" : term => `(1)', 'scoped syntax "x" : term',
    '@[simp, tactic x] def f := 1', '@[simp,\n  implemented_by g] def f := 1', '@[ extern "c" ] def f := 1',
    'attribute [local command_elab x] f', 'attribute\n  [init] f', 'open Lean in\nmacro "x" : term => `(1)',
    'theorem t : True := by\n  first | run_tac pure () | trivial', '-- a comment that says #eval', '/- IO -/',
]
ALLOWED = [
    'theorem t : True := trivial', 'theorem t : 2 + 2 = 4 := by decide', 'lemma t (a b : Nat) : a + b = b + a := by omega',
    'open Real Nat in\ntheorem t : True := trivial', 'set_option maxRecDepth 2000 in\ntheorem t : True := trivial',
    'private def helper (n : Nat) : Nat := n + 1', 'instance : Inhabited Nat := ⟨0⟩', 'local notation "‖" x "‖" => norm x',
    '@[simp] theorem t : True := trivial', '@[local simp] lemma t : True := trivial', 'attribute [local instance] foo',
    'noncomputable def f : Nat := Classical.choice ⟨0⟩', 'theorem t : x ∈ Set.Ioo 0 1 := sorry',
    # longer words that hold a refused one
    'def macros_done := 1', 'def elaborate := 1', 'def syntaxTree := 1', 'def IOO := 1', 'def myIO := 1', 'def unsafely := 1',
    'theorem t : True := by simp only [foo, -simprocs]', 'def initialized := 1', 'def f := x.run_cmds', 'def tactic := 1',
    'def init := 1', 'def extern := 1', 'theorem export_ok : True := trivial',
]

wrong = 0
for text in REFUSED:
    got = runs_code(text); good = got is not None; wrong += not good
    print("%-5s refused  %-58s %s" % ("ok" if good else "WRONG", text.replace("\n", " / ")[:58], "`%s`, %s" % (got[1], got[0]) if got else "it was let through"))
for text in ALLOWED:
    got = runs_code(text); good = got is None; wrong += not good
    print("%-5s allowed  %-58s %s" % ("ok" if good else "WRONG", text.replace("\n", " / ")[:58], "" if good else "refused for `%s`" % got[1]))
print("%d wrong" % wrong)
sys.exit(1 if wrong else 0)
