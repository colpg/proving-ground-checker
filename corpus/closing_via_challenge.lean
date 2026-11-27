import Cuts.xor2_le_5_by_mono
import Problems.xor2_le_4
import Proofs.size_mono

theorem Example.xor2_le_5 : Example.xor2_le_5.Statement := Example.xor2_le_5_by_mono Example.xor2_le_4 Example.size_mono
