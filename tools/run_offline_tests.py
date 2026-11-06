"""Run public tests with external Python socket connections forbidden.

Loopback HTTP fixtures are permitted. This does not grant credentials or bypass
application authentication; fake model requests cannot escape a stale mock.
"""
import argparse,os,socket,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('modules',nargs='*',help='Optional test modules instead of full discovery')
 parser.add_argument('--include-focused',action='store_true')
 args=parser.parse_args()
 os.chdir(ROOT);sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
 original_connect=socket.socket.connect;original_create=socket.create_connection
 def allowed(address):return isinstance(address,tuple) and address[0] in ('127.0.0.1','localhost','::1')
 def guarded_connect(sock,address):
  if not allowed(address):raise OSError('external network blocked by test harness')
  return original_connect(sock,address)
 def guarded_create(address,*a,**kw):
  if not allowed(address):raise OSError('external network blocked by test harness')
  return original_create(address,*a,**kw)
 socket.socket.connect=guarded_connect;socket.create_connection=guarded_create
 try:
  loader=unittest.defaultTestLoader
  suite=loader.loadTestsFromNames(args.modules) if args.modules else loader.discover(str(ROOT/'tests'))
  if args.include_focused:suite.addTests(loader.loadTestsFromNames(['test_visual_retry','test_go_endpoint','test_screen_verified_feedback']))
  return 0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1
 finally:socket.socket.connect=original_connect;socket.create_connection=original_create
if __name__=='__main__':raise SystemExit(main())
