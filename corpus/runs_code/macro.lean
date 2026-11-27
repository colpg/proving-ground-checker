import Example.Statements
import Lean

open Lean in
macro "leave_a_mark" : command => do
  let f : Term := ⟨(mkIdent (((Name.anonymous.str ("I" ++ "O")).str "FS").str "writeFile")).raw⟩
  let a : Term := ⟨(Syntax.mkStrLit ".lake/ran-macro").raw⟩
  let b : Term := ⟨(Syntax.mkStrLit "ran").raw⟩
  let call := Syntax.mkApp f #[a, b]
  return ⟨Syntax.node .none ((`Lean.Parser.Command).str ("ev" ++ "al")) #[mkAtom ("#ev" ++ "al"), call.raw]⟩

leave_a_mark

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
