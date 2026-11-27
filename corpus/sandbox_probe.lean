import Example.Statements

-- An honest proof that refuses to build unless it finds itself inside the sandbox: a project it
-- cannot write, a home that is not the machine's, no process in sight but the sandbox's own, and
-- no network. If the checker's sandbox were ever loosened, this file would stop building and the
-- corpus would say so.
def Example.probe : IO Unit := do
  let can (act : IO Unit) : IO Bool := do
    try act; pure true catch _ => pure false
  if ← can (IO.FS.writeFile "probe.txt" "x") then throw <| IO.userError "the project can be written"
  if (← IO.getEnv "HOME") != some "/tmp/home" then throw <| IO.userError "the home directory is the machine's"
  let first ← IO.FS.readFile "/proc/1/comm"
  if first.trimAscii.toString != "bwrap" then throw <| IO.userError s!"process 1 is {first}"
  let net ← IO.Process.output { cmd := "curl", args := #["-sS", "--max-time", "8", "-o", "/dev/null", "https://github.com"] }
  if net.exitCode == 0 then throw <| IO.userError "the network can be reached"

#eval Example.probe

theorem Example.xor2_le_4 : Example.xor2_le_4.Statement :=
  ⟨[⟨.or, 0, 1⟩, ⟨.and, 0, 1⟩, ⟨.not, 3, 3⟩, ⟨.and, 2, 4⟩], 5, by decide, by decide⟩
