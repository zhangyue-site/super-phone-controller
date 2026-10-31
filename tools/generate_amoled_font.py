"""Generate the checked-in Chinese font on the cloud workspace.
Requires fonttools and lv_font_conv. Input: NotoSansCJK-Regular.ttc (SIL OFL).
"""
from pathlib import Path
import argparse, subprocess, tempfile
from fontTools.ttLib import TTCollection
ap=argparse.ArgumentParser();ap.add_argument('font');args=ap.parse_args()
root=Path(__file__).resolve().parents[1]
chars=set((root/'firmware-amoled/main/main.c').read_text())
for code in range(0x4e00,0xa000):
    try: chr(code).encode('gb2312');chars.add(chr(code))
    except UnicodeEncodeError: pass
chars.update(chr(code) for start,end in [(0xa0,0x100),(0x3000,0x3040),(0xff00,0xfff0)] for code in range(start,end))
with tempfile.TemporaryDirectory() as td:
    font=Path(td)/'noto-sc.ttf'
    TTCollection(args.font).fonts[2].save(font)
    target=root/'firmware-amoled/main/ui_font.c'
    subprocess.run(['npx','--yes','lv_font_conv@1.5.3','--font',str(font),'--size','24','--bpp','4','--format','lvgl','--symbols',''.join(sorted(chars)),'--range','0x20-0x7e','--output',str(target)],check=True)
    s=target.read_text();a=s.index(' * Opts:');b=s.index(' ******************************************************************************/',a)
    s=s[:a]+' * Noto Sans CJK SC: GB2312 Chinese + UI/Latin punctuation, lv_font_conv 1.5.3.\n * SIL OFL, see LICENSE-NOTO. Regenerate using tools/generate_amoled_font.py.\n'+s[b:]
    target.write_text(s)
    print('font source bytes',target.stat().st_size,'requested glyphs',len(chars))
