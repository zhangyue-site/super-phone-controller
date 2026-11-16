"""Run synthetic Agent regressions without external or phone network access."""
import os,socket,sys,unittest
from pathlib import Path
def main():
 root=Path(__file__).resolve().parents[1];tests=root/"tests/agent_runtime"
 os.chdir(root);sys.path[:0]=[str(root),str(tests)]
 original=socket.socket.connect;create=socket.create_connection
 def blocked(*args,**kwargs):raise OSError("network disabled in Agent regression tests")
 socket.socket.connect=blocked;socket.create_connection=blocked
 try:return 0 if unittest.TextTestRunner().run(unittest.defaultTestLoader.discover(str(tests))).wasSuccessful() else 1
 finally:socket.socket.connect=original;socket.create_connection=create
if __name__=="__main__":raise SystemExit(main())
