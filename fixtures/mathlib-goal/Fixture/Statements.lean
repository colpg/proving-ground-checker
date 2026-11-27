import Mathlib

/-- The square root of two is irrational. -/
abbrev Fixture.sqrt_two_irrational.Statement : Prop := Irrational (Real.sqrt 2)
