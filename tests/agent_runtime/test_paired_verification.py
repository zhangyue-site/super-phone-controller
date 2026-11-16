import copy,unittest
from display_service import agent_runtime as r
import test_verify_contract as fixtures
class PairedVerification(unittest.TestCase):
 def test_brightness_verifier_receives_current_then_same_scope_before(self):
  fixture=fixtures.VerificationContract();hint,info=fixture.fixtures("adjust_brightness")
  info["_action_before_image"]=dict(jpeg=b"before-original",observation=copy.deepcopy(hint["_observation"]))
  requests=[]
  def model(p):
   requests.append(p)
   return dict(safe=True,done=True,step_verified=True,evidence="前后画面确认亮度改变且其他开关未变",step=None)
  r.observe_plan(b"current-original",hint,info,verify=True,model=model,vision_model=fixture.visual)
  images=[c["image_url"]["url"]for c in requests[0]["messages"][1]["content"]if c["type"]=="image_url"]
  import base64
  self.assertEqual([base64.b64decode(x.split(",",1)[1])for x in images],[b"current-original",b"before-original"])
 def test_cross_task_session_device_lease_geometry_comparison_rejected(self):
  hint,info=fixtures.VerificationContract().fixtures("adjust_brightness")
  for key in ("task_id","device_id","capture_session","binding_id","geometry"):
   before=copy.deepcopy(hint["_observation"]);before[key]="different"
   self.assertIsNone(r._comparison_before(dict(_action_before_image=dict(jpeg=b"old",observation=before)),hint))
 def test_no_before_means_no_fabricated_comparison(self):
  hint,info=fixtures.VerificationContract().fixtures("adjust_brightness")
  self.assertIsNone(r._comparison_before(info,hint))
