from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/"ota-test"
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Wno-unused-parameter","-Werror","-fsanitize=address,undefined","-g","-I",str(r/"firmware-amoled/main"),str(r/"tests/amoled_ota_engine_test.c"),str(r/"firmware-amoled/main/ota_engine.c"),"-o",str(p)],check=True)
 subprocess.run([str(p)],check=True)
