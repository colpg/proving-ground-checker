import Example.Statements

-- An answer that never finishes building. That is a rejection, and it counts: the machine is
-- working, and the time went to the answer.
partial def Example.spin (n : Nat) : Nat := Example.spin (n + 1)

#eval Example.spin 0

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
