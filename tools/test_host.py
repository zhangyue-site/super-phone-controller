"""Run firmware's platform-independent regression tests with a host C++ compiler."""
from pathlib import Path
import subprocess, tempfile
ROOT=Path(__file__).resolve().parents[1]
def needs_idf(text):
    return '#include "esp_' in text or '#include <esp_' in text
with tempfile.TemporaryDirectory() as temp:
    for test in sorted(list((ROOT/'tests').glob('*_test.cpp'))+list((ROOT/'tests').glob('*_test.c'))):
        binary=str(Path(temp)/test.stem)
        compiler,standard=('cc','-std=c11') if test.suffix=='.c' else ('c++','-std=c++17')
        # AMOLED tests live in their own tree: use that include path and link the
        # matching unit (amoled_foo_test -> firmware-amoled/main/foo.c).
        module='firmware-amoled/main' if test.stem.startswith('amoled_') else 'firmware-epaper/main'
        unit=None
        if test.stem.startswith('amoled_'):
            candidate=ROOT/'firmware-amoled/main'/(test.stem[len('amoled_'):-len('_test')]+'.c')
            if candidate.exists():unit=candidate
        # Some AMOLED units pull in ESP-IDF headers (esp_err.h) and can only be
        # built inside the IDF container. Skip loudly instead of failing the run.
        sources=[test]+([unit] if unit else [])
        if any(needs_idf(s.read_text(errors='ignore')) for s in sources):
            print(test.name, 'SKIP requires ESP-IDF');continue
        cmd=[compiler,standard,'-I',str(ROOT/module),str(test)]
        if test.stem=='interaction_test':cmd.append(str(ROOT/'firmware-epaper/main/gesture.cpp'))
        if unit:cmd.append(str(unit))
        if test.stem in ('ota_resume_policy_test','power_key_policy_test'):
            # ota_guard.c is C++ in disguise (<stdatomic.h> + bool); C++23 gives
            # atomic_uint, and compiling it as C fails on purpose-built types.
            cmd=[compiler,'-std=c++23','-I',str(ROOT/module),str(test),'-x','c++',str(ROOT/'firmware-epaper/main/ota_guard.c')]
        if test.stem=='no_adb_transport_test':
            # Builds adb_local.cpp with every CONFIG_* undefined to exercise the
            # "ADB disabled" fallbacks that production never links.
            cmd=[compiler,standard,'-I',str(ROOT/'tests/fixtures/adb_disabled'),'-I',str(ROOT/module),
                 str(test),str(ROOT/'firmware-epaper/main/adb_local.cpp')]
        subprocess.run(cmd+['-o',binary],check=True)
        subprocess.run([binary],check=True)
        print(test.name, 'PASS')
