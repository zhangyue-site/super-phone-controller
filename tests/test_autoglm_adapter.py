import unittest,base64,io
from PIL import Image
from display_service.autoglm_adapter import screenshot,translate,search_result_verified
from display_service.dialogue import parse_observation
from test_dialogue import XML
class AutoGLMTests(unittest.TestCase):
 def test_image_rejects_non_image(self):
  with self.assertRaises(ValueError):screenshot(base64.b64encode(b"bad").decode())
 def test_image_limits_and_decodes(self):
  b=io.BytesIO();Image.new("RGB",(1080,2400)).save(b,format="PNG")
  data,w,h=screenshot(base64.b64encode(b.getvalue()).decode());self.assertEqual((w,h),(1080,2400));self.assertTrue(data)
 def test_launch_uses_observed_component(self):
  o=parse_observation(XML);o['apps']=['com.tencent.mm/.ui.LauncherUI']
  self.assertEqual(translate({'action':'Launch','app':'微信'},o,'打开微信找测试联系人')['op'],'launch')
 def test_type_requires_search_field_and_user_text(self):
  o=parse_observation(XML)
  with self.assertRaises(ValueError):translate({'action':'Type','text':'测试联系人'},o,'打开微信找测试联系人')
  o['nodes'][0].update(editable=True,focused=True,label='搜索',password=False)
  self.assertEqual(translate({'action':'Type','text':'测试联系人'},o,'打开微信找测试联系人')['op'],'type_text')
  with self.assertRaises(ValueError):translate({'action':'Type','text':'发送其他文字'},o,'打开微信找测试联系人')
 def test_sensitive_tap_rejected(self):
  o=parse_observation(XML);o['size']=[1080,2400];o['nodes'][0]['label']='发送'
  with self.assertRaises(ValueError):translate({'action':'Tap','element':[500,500]},o,'打开微信找测试联系人')

 def test_no_results_is_not_contact_found(self):
  o={'nodes':[{'editable':True,'own_label':'测试联系人'},{'own_label':'联系人'},{'own_label':'未找到测试联系人'}]}
  self.assertFalse(search_result_verified(o,'测试联系人'))
  o['nodes'][-1]['own_label']='测试联系人';self.assertTrue(search_result_verified(o,'测试联系人'))
 def test_search_input_or_history_alone_is_not_result(self):
  self.assertFalse(search_result_verified({'nodes':[{'editable':True,'own_label':'测试联系人'},{'own_label':'搜索历史'},{'own_label':'测试联系人'}]},'测试联系人'))
