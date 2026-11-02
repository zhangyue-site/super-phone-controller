from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 out=Path(d)/"test"
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I",str(root/"firmware-amoled/main"),str(root/"tests/amoled_audio_policy_test.c"),str(root/"firmware-amoled/main/audio_policy.c"),"-o",str(out)],check=True)
 subprocess.run([str(out)],check=True)
print("Audio PCM budget: explicit start, epoch cancellation, even frames, 0.4–10s and silence passed")
