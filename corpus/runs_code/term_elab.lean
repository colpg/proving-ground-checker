import Example.Statements
import Lean

open Lean Elab Term

syntax (name := markTerm) "mark_term" : term

@[term_elab markTerm] def markTermImpl : TermElab := fun _ _ => do
  IO.FS.writeFile ".lake/ran-term_elab" "ran"
  return mkConst ``True.intro

example : True := mark_term

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
