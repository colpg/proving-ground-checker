import Example.Statements
import Lean

open Lean Elab Command

syntax (name := leaveAMark) "leave_a_mark" : command

@[command_elab leaveAMark] def leaveAMarkImpl : CommandElab := fun _ => IO.FS.writeFile ".lake/ran-command_elab" "ran"

leave_a_mark

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
