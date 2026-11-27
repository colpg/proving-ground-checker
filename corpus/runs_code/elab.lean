import Example.Statements
import Lean

elab "leave_a_mark" : command => IO.FS.writeFile ".lake/ran-elab" "ran"

leave_a_mark

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
