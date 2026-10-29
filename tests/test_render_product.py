"""Pure rendering checks. Run with Python + Pillow and EPAPER_FONT if needed."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

from display_service import render as m

class RenderTests(unittest.TestCase):
    def check(self,im):
        self.assertEqual(('1',(200,200),5000),(im.mode,im.size,len(im.tobytes())))
    def test_quota_missing_stale_error_long_value(self):
        rows=[dict(label='渠道',value=value,remaining=None,status=status,age=age)
              for value,status,age in [('76%','ok',60),('--','unavailable',None),('12%','stale',7200),('45%','error',1800),('USD 123456.78','ok',125)]]
        original=[dict(row) for row in rows]
        self.check(m.render(rows,{},now=1793250000))
        self.assertEqual(rows,original)
    def test_task_states(self):
        for state in ['idle','listening','thinking','running','waiting','done','error','stopped','unknown']:
            self.check(m.render([],dict(state=state,task='很长的中文任务内容'*15,step=2),page=1,connected=False))
    def test_voice_unchanged_format(self):
        self.check(m.render_dialogue('请在手机检查结果','waiting'))
        self.check(m.render_voice_ui(SimpleNamespace(state='plan',ui_heard='打开应用',ui_plan=['打开应用'],done=False)))
    def test_footer_boundary(self):
        from PIL import Image, ImageChops
        import re
        header=(Path(__file__).parent/'product_screens.168.h').read_text()
        encoded=header.split('product_footer',1)[1].split('=',1)[1].split(';',1)[0]
        values=list(map(int,re.findall(r'\d+',encoded)))
        self.assertGreaterEqual(len(values),650)
        footer=Image.frombytes('1',(200,26),bytes(values[:650]))
        rows=[dict(label='Codex '+str(i),value='76%',status='ok',age=60) for i in range(4)]
        rows.append(dict(label='Jev',value='USD 123456.78',status='stale',age=7200))
        for name,raw in [('quota',m.render(rows,{},now=1793250000)),
                         ('record',m.render([],dict(state='error',task='键盘输入未完成，请在手机检查输入框',updatedAt=1793250000),page=1))]:
            self.assertIsNone(ImageChops.difference(raw.crop((0,162,200,200)),Image.new('1',(200,38),1)).getbbox())
            merged=raw.copy();merged.paste(footer,(0,162))
            self.assertEqual(raw.crop((0,0,200,162)).tobytes(),merged.crop((0,0,200,162)).tobytes())
            if name=='quota':
                self.assertIsNotNone(ImageChops.difference(raw.crop((0,136,200,161)),Image.new('1',(200,25),1)).getbbox())
            output=Path(__file__).resolve().parents[2]/'previews'
            output.mkdir(exist_ok=True)
            raw.save(output/('product-ui-'+name+'-162-raw.png'))
            merged.save(output/('product-ui-'+name+'-168-final.png'))

if __name__=='__main__':unittest.main()
