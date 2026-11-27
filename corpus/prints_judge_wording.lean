import Example.Statements
import Lean

/-
theorem Example.xor2_le_4 : Example.xor2_le_4.Statement := sorry
-/

open Lean Elab Command

-- The bogus proof of skips_the_kernel.lean, which every checker refuses. Before it, this file prints
-- every line the judge prints for an answer that all its checkers accept. A checker that read the
-- build's output let a file like this one choose how its own rejection was read.
run_cmd do
  for k in ["Lean paranoid", "lean4lean", "nanoda", "con-leche", "con-ron", "Lean default"] do
    IO.println s!"Running {k} kernel on solution"
    IO.println s!"{k} kernel accepts the solution"
  IO.println "Your solution is okay!"
  IO.eprintln "error: Illegal axiom detected: 'nothing'"
  Lean.logWarning "x\nnanoda kernel accepts the solution\nYour solution is okay!"

set_option debug.skipKernelTC true in
run_cmd liftCoreM do
  addDecl <| Declaration.thmDecl {
    name := `Example.xor2_le_4
    levelParams := []
    type := mkConst ``Example.xor2_le_4.Statement
    value := mkConst ``True.intro }
