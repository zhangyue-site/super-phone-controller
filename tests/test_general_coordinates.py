import unittest
from display_service.general_vision import normalize_observation
class CoordinatesTests(unittest.TestCase):
 def test_real_image_pixels_map_camera_center(self):
  r=normalize_observation({'coordinate_system':'pixels','bounds':[517,953,601,1034],'end':[559,994]},640,1280)
  self.assertEqual(r['bounds'],[807,744,939,807]);self.assertEqual(r['end'],[873,776])
 def test_no_clamping_outside_image(self):
  with self.assertRaises(ValueError):normalize_observation({'coordinate_system':'pixels','bounds':[0,0,641,1200]},640,1280)
 def test_ambiguous_units_rejected(self):
  with self.assertRaises(ValueError):normalize_observation({'bounds':[1,2,3,4]},640,1280)
