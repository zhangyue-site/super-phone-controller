"""Maintenance client contracts; no BLE adapter, credentials, or phone required."""
import asyncio, importlib.util, pathlib, unittest
from unittest.mock import AsyncMock
spec=importlib.util.spec_from_file_location('ble_direct',pathlib.Path(__file__).resolve().parents[1]/'tools/ble_direct_client.py')
client=importlib.util.module_from_spec(spec)
# Keep the optional hardware dependency out of protocol-only tests.
import sys,types
from unittest.mock import patch
with patch.dict(sys.modules,{'bleak':types.SimpleNamespace(BleakClient=None,BleakScanner=None)}):spec.loader.exec_module(client)

class ClientTests(unittest.IsolatedAsyncioTestCase):
 async def test_invalid_parameters_never_reach_att_or_consume_sequence(self):
  for op,args in [(3,(65535,1,0,0,0)),(3,(True,1,0,0,0)),(4,(0,0,1,1,99)),(1,(1,0,0,0,0)),(99,(0,0,0,0,0))]:
   with self.subTest(op=op,args=args):
    transport=types.SimpleNamespace(write_gatt_char=AsyncMock())
    link=client.Link(transport,'unused');link.key=b'synthetic';link.read=AsyncMock(return_value=dict(seq=1,op=op,busy=0,result=3))
    with self.assertRaises(ValueError):await link.send(op,args)
    transport.write_gatt_char.assert_not_awaited();self.assertEqual(link.seq,0)
 async def test_receipt_must_match_operation_not_just_sequence(self):
  transport=types.SimpleNamespace(write_gatt_char=AsyncMock())
  link=client.Link(transport,'unused');link.key=b'synthetic';link.read=AsyncMock(return_value=dict(seq=1,op=2,busy=0,result=3))
  with self.assertRaisesRegex(RuntimeError,'operation'):await link.send(1)
  self.assertEqual(transport.write_gatt_char.await_count,1)
 async def test_arm_returns_only_when_usb_hid_is_ready(self):
  link=client.Link(types.SimpleNamespace(),'unused');link.send=AsyncMock(return_value=(dict(seq=1,op=6,result=7,hid=0,busy=0,ready=0),b''));settled=dict(seq=1,op=6,result=7,hid=1,busy=0,ready=1);link.hid=AsyncMock(return_value=settled)
  self.assertEqual(await link.command(6),settled);link.hid.assert_awaited_once_with(1)
 async def test_rejected_arm_does_not_wait_or_report_ready(self):
  link=client.Link(types.SimpleNamespace(),'unused');link.send=AsyncMock(return_value=(dict(result=4),b''));link.hid=AsyncMock()
  with self.assertRaises(RuntimeError):await link.command(6)
  link.hid.assert_not_awaited()
 async def test_command_failure_is_explicit_and_not_retried(self):
  for result in (4,5,6):
   link=client.Link(types.SimpleNamespace(),'unused');link.send=AsyncMock(return_value=(dict(result=result),b''))
   with self.assertRaises(RuntimeError):await link.command(3,(10,20,0,0,0))
   self.assertEqual(link.send.await_count,1)
 async def test_stop_cancellation_is_successful_stop_not_failed_click(self):
  link=client.Link(types.SimpleNamespace(),'unused');link.send=AsyncMock(return_value=(dict(result=5,hid=0),b''))
  self.assertEqual((await link.command(5))['result'],5)
