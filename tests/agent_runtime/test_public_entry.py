import os,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from display_service.conversation import Conversation

class PublicEntry(unittest.TestCase):
 def job(self,enabled):
  job=SimpleNamespace();conversation=object.__new__(Conversation)
  conversation.mailbox=SimpleNamespace(create=Mock(return_value=job))
  with patch.dict(os.environ,{"EPAPER_PHONE_AGENT":enabled}),patch("display_service.conversation.threading.Thread") as thread:
   result=conversation.start_remote("synthetic-board","synthetic-session",4,"打开设置","a"*32,"absolute-v1","synthetic-lease")
  self.assertIs(result,job);conversation.mailbox.create.assert_called_once_with("synthetic-board","synthetic-session",4)
  self.assertEqual(job.remote_task_id,"a"*32);self.assertEqual(job.remote_lease,"synthetic-lease")
  self.assertEqual(job.pointer_protocol,"absolute-v1");thread.return_value.start.assert_called_once()
  self.assertEqual(thread.call_args.kwargs["args"],(job,"打开设置"))
  return job
 def test_enabled_agent_remote_entry_preserves_task_and_authority_context(self):
  job=self.job("1");self.assertTrue(job.agent_job);self.assertEqual(job.max_age,600)
 def test_legacy_entry_does_not_enable_generic_agent_implicitly(self):
  job=self.job("0");self.assertFalse(getattr(job,"agent_job",False))
