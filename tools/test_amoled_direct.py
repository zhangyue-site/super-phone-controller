from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 out=Path(d)/"direct-test"
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I",str(root/"firmware-amoled/main"),str(root/"tests/amoled_direct_policy_test.c"),str(root/"firmware-amoled/main/direct_policy.c"),"-o",str(out)],check=True)
 subprocess.run([str(out)],check=True)
print("AMOLED direct policy: lease, owner, local consent, expiry, ID retirement and STOP passed")
