import Example.Statements

-- While it builds, this answer writes files under .lake for as long as it is allowed to. Left
-- alone it would fill the machine's disk, and the control that runs after it would fail. The build
-- is stopped when the disk runs short, and that is a rejection, not a fault.
#eval show IO Unit from do
  let block := String.mk (List.replicate (1 <<< 20) 'x')
  for i in [0:1000000] do
    let h ← IO.FS.Handle.mk s!".lake/fill-{i}" .write
    for _ in [0:64] do h.putStr block
    h.flush

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
