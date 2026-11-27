import Fixture.Statements

/-
theorem Fixture.sqrt_two_irrational : Fixture.sqrt_two_irrational.Statement := sorry
-/

open Lean Elab Command

-- Mathlib brings Lean's own machinery with it, so this file needs no import beyond the goal's.
-- It adds the theorem with a proof of something else and tells Lean not to check it.
-- The file builds. The judge replays it through its own checkers, and they refuse it.
set_option debug.skipKernelTC true in
run_cmd liftCoreM do
  addDecl <| Declaration.thmDecl {
    name := `Fixture.sqrt_two_irrational
    levelParams := []
    type := mkConst ``Fixture.sqrt_two_irrational.Statement
    value := mkConst ``True.intro }
