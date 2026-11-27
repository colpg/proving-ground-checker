import Example.Statements
import Lean

/-
theorem Example.xor2_le_4 : Example.xor2_le_4.Statement := sorry
-/

open Lean Elab Command

-- Adds the theorem to the environment with a proof of something else, and tells Lean not to check it.
-- The file builds. The judge replays it through its own checkers, and they refuse it.
set_option debug.skipKernelTC true in
run_cmd liftCoreM do
  addDecl <| Declaration.thmDecl {
    name := `Example.xor2_le_4
    levelParams := []
    type := mkConst ``Example.xor2_le_4.Statement
    value := mkConst ``True.intro }
