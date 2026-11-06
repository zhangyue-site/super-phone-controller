"""OCR 快速定位前置：RapidOCR 优先，未命中或服务异常时静默落回 VLM。
只处理"在截图中找到目标文字并给出点击坐标"这一种观察，其余全部交还 VLM。
开关：EPAPER_OCR_URL（默认 http://127.0.0.1:8792），token 文件 EPAPER_OCR_TOKEN_FILE。
"""
import base64,json,math,os,re,urllib.request
from pathlib import Path

_URL=os.environ.get('EPAPER_OCR_URL','http://127.0.0.1:8792')
_TOKEN_FILE=os.environ.get('EPAPER_OCR_TOKEN_FILE','')
_TIMEOUT=float(os.environ.get('EPAPER_OCR_TIMEOUT','3'))
_STRIP=re.compile(r'^(?:请|帮我)?(?:打开|进入|搜索|查找|找到|返回|回到)')
_SAFE=re.compile(r'^[0-9A-Za-z\u4e00-\u9fff]{1,16}$')

def extract_target(task):
 if not isinstance(task,str):return None
 t=_STRIP.sub('',task.strip()).strip()
 return t if t and _SAFE.fullmatch(t) else None

def ocr_observe(raw,task):
 """返回与 general_vision 同构的 observation dict；不适用/未命中/异常一律返回 None。"""
 target=extract_target(task)
 if not target or not isinstance(raw,bytes) or not raw:return None
 try:
  token=Path(_TOKEN_FILE).read_text().strip() if _TOKEN_FILE else ''
  body=json.dumps({'image_b64':base64.b64encode(raw).decode(),'target':target,'mode':'fuzzy'}).encode()
  req=urllib.request.Request(_URL.rstrip('/')+'/find',body,{'X-Ocr-Token':token,'Content-Type':'application/json'})
  result=json.load(urllib.request.urlopen(req,timeout=_TIMEOUT))
 except Exception:return None  # OCR 链路任何故障都不影响 VLM 主链
 if not isinstance(result,dict):return None
 hit=result.get('hit')
 if not isinstance(hit,dict) or hit.get('text')!=target:return None
 score=hit.get('score')
 if type(score) not in (int,float) or not math.isfinite(score) or not .8<=score<=1:return None
 from PIL import Image
 import io
 try:width,height=Image.open(io.BytesIO(raw)).size
 except Exception:return None
 bounds=hit.get('bounds')
 if not isinstance(bounds,list) or len(bounds)!=4 or any(type(x) is not int for x in bounds):return None
 x1,y1,x2,y2=bounds
 if not 0<=x1<x2<=width or not 0<=y1<y2<=height:return None
 return {'coordinate_system':'pixels','safe':True,'complete':False,
  'screen':'ocr','action':'click',
  'bounds':[x1*1000//width,y1*1000//height,x2*1000//width,y2*1000//height],
  'target_label':hit['text'],'ocr':True,'ocr_ms':result.get('ms')}
