import Example.Statements
import Lean

open Lean Meta Simp

simproc leaveAMark (_ + _) := fun _ => do
  IO.FS.writeFile ".lake/ran-simproc" "ran"
  return .continue

example (a b : Nat) : a + b = a + b := by simp

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
