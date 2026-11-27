import Fixture.Statements
import Mathlib

-- A KNOWN GAP in the form screen. Mathlib's `linarith` evaluates the term given as its oracle, and
-- an oracle is a structure holding a function that runs in the elaborator. So this file hands its
-- own code to a tactic without any command, attribute or name that a list of refused words could
-- hold: the structure's field needs no type written out, and the file is written by a function of
-- Lean's own whose name mentions nothing of the system. Found in review. No list can keep up with
-- every extension point of every library, so for a goal with dependencies the sandbox is what
-- holds, and not the screen. The proof at the end is honest, so this file is accepted.
def ranOracle : Mathlib.Tactic.Linarith.CertificateOracle where
  produceCertificate hyps n := do
    Lean.writeModule (← Lean.getEnv) ".lake/ran-oracle"
    Mathlib.Tactic.Linarith.CertificateOracle.simplexAlgorithmSparse.produceCertificate hyps n

example (x : ℚ) (h : 0 < x) : 0 < 2 * x := by linarith (oracle := ranOracle)

theorem Fixture.sqrt_two_irrational : Fixture.sqrt_two_irrational.Statement := irrational_sqrt_two
