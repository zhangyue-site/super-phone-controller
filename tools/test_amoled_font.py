"""Check actual LVGL cmap coverage for every non-ASCII main.c UI character.

Uses the same source-character input as generate_amoled_font.py, without needing
fonttools/npm/font files or trusting bitmap comments as a character map.
"""
from pathlib import Path
import re,unittest

def covered(font):
 arrays={}
 for match in re.finditer(r"static const uint(?:8|16|32)_t (\w+)\[\] = \{(.*?)\};",font,re.S):
  body=re.sub(r"/\*.*?\*/","",match[2],flags=re.S)
  arrays[match[1]]=[int(n,0) for n in re.findall(r"0x[0-9a-fA-F]+|\b[0-9]+\b",body)]
 maps=re.search(r"static const lv_font_fmt_txt_cmap_t cmaps\[\] =\s*\{(.*?)\n\};",font,re.S)
 if not maps:raise ValueError("LVGL cmap missing")
 result=set()
 for block in re.findall(r"\{([^{}]+)\}",maps[1]):
  def field(name):
   match=re.search(r"\."+name+r"\s*=\s*([\w]+)",block)
   if not match:raise ValueError("missing cmap field "+name)
   return match[1]
  start,length=int(field("range_start")),int(field("range_length"))
  kind=field("type")
  if kind=="LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY":
   result.update(range(start,start+length))
  elif kind=="LV_FONT_FMT_TXT_CMAP_FORMAT0_FULL":
   offsets=arrays[field("glyph_id_ofs_list")]
   if len(offsets)!=length:raise ValueError("cmap offset length")
   result.update(start+i for i,value in enumerate(offsets) if value or i==0)
  elif kind=="LV_FONT_FMT_TXT_CMAP_SPARSE_TINY":
   offsets=arrays[field("unicode_list")]
   if len(offsets)!=int(field("list_length")):raise ValueError("cmap sparse length")
   result.update(start+value for value in offsets)
  else:raise ValueError("unhandled cmap "+kind)
 return result

def missing(source,font):
 return {ord(c) for c in source if ord(c)>127}-covered(font)

class CmapChecks(unittest.TestCase):
 def test_missing_and_full_holes_are_detected(self):
  font="""static const uint8_t offsets[] = {0, 0, 1};
static const lv_font_fmt_txt_cmap_t cmaps[] =
{
 { .range_start = 304, .range_length = 3, .glyph_id_start = 1,
 .unicode_list = NULL, .glyph_id_ofs_list = offsets, .list_length = 3, .type = LV_FONT_FMT_TXT_CMAP_FORMAT0_FULL }
};
"""
  self.assertEqual(covered(font),{304,306})
  self.assertEqual(missing(chr(305),font),{305})
 def test_current_ui_is_covered(self):
  root=Path(__file__).resolve().parents[1]
  source=(root/"firmware-amoled/main/main.c").read_text()
  font=(root/"firmware-amoled/main/ui_font.c").read_text()
  absent=missing(source,font)
  self.assertFalse(absent,"Missing UI glyphs: "+", ".join(f"U+{cp:04X} {chr(cp)}" for cp in sorted(absent)))
  for char in "直连本地许可已开启等待确认任务":self.assertIn(ord(char),covered(font))

if __name__=="__main__":unittest.main()

