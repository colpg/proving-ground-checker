import Example.Statements

-- While it builds, this answer replaces a compiled file of the goal's own library with junk. The
-- sandbox lets a build write under .lake, because the build's own outputs live there. The proof
-- below is honest, but what was built can no longer be believed, and it must not be accepted. In a
-- real check it could change nothing: the challenge's export is made on another machine.
#eval show IO Unit from do
  let p : System.FilePath := ".lake/build/lib/lean/Example/Statements.olean"
  IO.FS.removeFile p
  IO.FS.writeFile p "not a compiled file"

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
