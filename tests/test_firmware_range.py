import http.client,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from display_service import app,firmware
class RangeHTTPTests(unittest.TestCase):
 def test_authenticated_resume_and_exact_headers(self):
  payload=bytes(range(256))*16
  with tempfile.TemporaryDirectory() as d:
   cfg=Path(d)/'devices.json';cfg.write_text(json.dumps({'one':'private-test-key'}))
   server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);thread=threading.Thread(target=server.serve_forever);thread.start()
   def get(range_value=None,key='private-test-key'):
    c=http.client.HTTPConnection(*server.server_address,timeout=5);headers={'Authorization':'Bearer '+key}
    if range_value is not None:headers['Range']=range_value
    c.request('GET','/firmware/image?sha='+'a'*64,headers=headers);r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result
   try:
    with patch.object(app,'CONFIG',cfg),patch.object(firmware,'release',return_value=({},payload)):
     code,h,data=get();self.assertEqual((code,data),(200,payload));self.assertEqual(h['Accept-Ranges'],'bytes')
     code,h,data=get('bytes=163-');self.assertEqual((code,data),(206,payload[163:]));self.assertEqual(h['Content-Range'],'bytes 163-4095/4096');self.assertEqual(int(h['Content-Length']),len(payload)-163)
     self.assertEqual(payload[:163]+data,payload)
     self.assertEqual(get('bytes=0-')[0],206)
     for bad in ('bytes=4096-','bytes=-1','bytes=1-2','bytes=1-,3-','bytes=01-','garbage'):
      code,h,data=get(bad);self.assertEqual(code,416);self.assertEqual(h['Content-Range'],'bytes */4096');self.assertEqual(data,b'')
     self.assertEqual(get('bytes=1-',key='wrong')[0],401)
   finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
