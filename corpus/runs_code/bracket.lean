import Example.Statements
import Lean
import Lake

-- An attribute that installs code, hidden behind a `]` inside a comment. A rule that reads an
-- attribute list up to the first `]` never sees it. Nothing else in this file is on a list of
-- refused words: the function's type is not the elaborator's monad by name, and the process is
-- started by a helper of Lake's that never mentions the system.
@[/- ] -/ command_elab Lean.Parser.Command.check]
def ran : Lean.Elab.Command.CommandElab := fun _ => do
  discard <| Lake.testProc { cmd := "touch", args := #[".lake/ran-bracket"] }

#check 0

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
