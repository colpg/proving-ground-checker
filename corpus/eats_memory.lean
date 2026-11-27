import Example.Statements

-- While it builds, this answer doubles an array until the machine has no memory left. The build
-- runs in a control group with a limit on memory, so it is the build that is stopped and not the
-- machine, and that is a rejection, not a fault.
#eval show IO Unit from do
  let mut a : Array Nat := Array.range 1000000
  for _ in [0:24] do
    a := a ++ a
  IO.println a.size

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
