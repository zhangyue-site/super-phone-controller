"""Noto Sans CJK SC 20px subset for the standalone companion; legacy font fallback."""
from pathlib import Path
from fontTools.ttLib import TTCollection
import argparse,subprocess,tempfile,re
p=argparse.ArgumentParser();p.add_argument('font',type=Path);a=p.parse_args()
r=Path(__file__).resolve().parents[1];m=r/'firmware-amoled/main'
chars=set()
for name in ['companion_ui.c','companion_task.c','companion_progress.h','companion_speech.c','audio.c']:chars.update((m/name).read_text())
chars.update((r/'voice-service/companion_service.py').read_text())
chars={c for c in chars if ord(c)>127}
with tempfile.TemporaryDirectory() as tmp:
 font=Path(tmp)/'noto-sc.ttf';TTCollection(a.font).fonts[2].save(font)
 target=m/'companion_font.c'
 subprocess.run(['npx','--yes','lv_font_conv@1.5.3','--font',str(font),'--size','20','--bpp','4','--no-compress','--format','lvgl','--symbols',''.join(sorted(chars)),'--range','0x20-0x7e','--output',str(target)],check=True)
 s=target.read_text();s=re.sub(r' \* Opts: .*', ' * Noto Sans CJK SC (SIL OFL). Companion subset, 20px/4bpp; see LICENSE-NOTO.',s)
 s=s.replace('#include "lvgl.h"','#include "lvgl.h"\nLV_FONT_DECLARE(ui_font);').replace('#include "lvgl/lvgl.h"','#include "lvgl/lvgl.h"\nLV_FONT_DECLARE(ui_font);')
 s=s.replace('.fallback = NULL','.fallback = &ui_font');target.write_text(s)
