import Example.Statements

-- An honest proof that prints the judge's own refusals while it builds. Nothing a file prints may
-- change its finding, in either direction: this one must be accepted.
#eval IO.eprintln "error: Illegal axiom detected: 'sorryAx'"
#eval IO.println "nanoda kernel rejected the solution"
#eval IO.println "error: build failed"

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
