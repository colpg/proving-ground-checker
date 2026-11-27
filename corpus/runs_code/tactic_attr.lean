import Example.Statements
import Lean

open Lean Elab Tactic

syntax (name := markTac) "mark_tac" : tactic

@[tactic markTac] def markTacImpl : Tactic := fun _ => IO.FS.writeFile ".lake/ran-tactic_attr" "ran"

example : True := by
  mark_tac
  trivial

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
