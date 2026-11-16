"""OCR context decides when to refresh a scene, never whether to send input."""
from .agent_scene_context import build

def context(hint):
 value=build(hint)
 return sorted(value["anchors"]) if value else []

def changed(previous,current):
 if previous is None:return bool(current)
 before,after=set(previous),set(current)
 if before==after:return False
 if not before or not after:return True
 return len(before & after)/max(len(before),len(after))<.65
