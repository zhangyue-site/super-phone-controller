"""Queued diagnostics observe existing leases without acquiring or renewing them."""
import copy
import json
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from display_service import app_screen, events, relay_http
from display_service.app_ota import Authority
from display_service.hid_relay import Relay
from display_service.relay_http import Gateway
from display_service.remote_control import RemoteControl
from test_hid_relay import KEY, NONCE, receipt
from test_remote_control import FakeConversation


class QueuedDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 100.0
        self.device = 'epaper-01'
        self.owner = ('android-app', 'private-owner', 'private-owner', self.device)
        self.conversation = FakeConversation()
        self.remote = RemoteControl(self.conversation, Path(self.tmp.name) / 'task.json',
                                    clock=lambda: self.now, screen_ready=lambda _: True)
        self.authority = Authority(clock=lambda: self.now)
        self.authority.tickets['private-capture-ticket'] = (400.0, self.device, 'usb-screen')
        self.relay = Relay(Path(self.tmp.name) / 'relay.db', lambda _: KEY, clock=lambda: self.now)
        self.addCleanup(self.relay.close)
        self.gateway = Gateway(self.relay, self.remote)
        for obj, name, value in ((app_screen, 'AUTHORITY', self.authority),
                                 (relay_http, 'GATEWAY', self.gateway)):
            guard = patch.object(obj, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        self.gateway.attach(self.device, self.owner[1], receipt())
        self.gateway.poll(self.device, self.owner[1], NONCE)
        self.ident = self.remote.prepare(self.owner, '打开设置')['task_id']
        self.remote.confirm(self.owner, self.ident)

    def status(self):
        return self.remote.status(self.owner, self.ident)

    def snapshot_state(self):
        return dict(
            sessions=copy.deepcopy(self.relay.sessions), turns=copy.deepcopy(self.gateway.turns),
            windows=copy.deepcopy(self.gateway.windows.windows),
            database=list(self.relay.db.iterdump()), changes=self.relay.db.total_changes,
            records=copy.deepcopy(self.remote.records), state_file=self.remote.path.read_bytes(),
            boots=copy.deepcopy(self.remote.boots), pending=copy.deepcopy(self.remote.pending_boots),
            board_turns=copy.deepcopy(self.remote.board_turns),
            tickets=copy.deepcopy(self.authority.tickets), challenges=copy.deepcopy(self.authority.challenges),
            nonces=copy.deepcopy(self.authority.upgrade_nonces), rates=copy.deepcopy(self.authority.rates),
            started=list(self.conversation.started), mailbox_high=copy.deepcopy(self.conversation.mailbox.high),
            commands=[(j.session, j.sequence, copy.deepcopy(j.command), j.delivered, j.result,
                       j.touched, j.video_sequence, j.cancelled, j.done)
                      for j in self.conversation.mailbox.jobs.values()])

    def test_main_without_latest_exec_can_report_queued_status(self):
        with patch.dict(events.__dict__):
            events.__dict__.pop('latest_exec', None)
            out = self.status()
        self.assertEqual(out['state'], 'queued')
        self.assertTrue(out['diagnostics']['deviceShareAuthorized'])
        self.assertEqual(out['diagnostics']['boardDirectState'], 'unknown')
        self.assertFalse(out['verified'])

    def test_recent_app_relay_does_not_require_a_board_heartbeat(self):
        with patch.object(events, 'latest_exec', return_value=None, create=True) as legacy:
            out = self.status()
            self.assertNotIn('没有板端心跳', out['reply'])
            legacy.assert_not_called()
        self.assertEqual(out['diagnostics']['relayState'], 'recent')
        self.assertEqual(out['diagnostics']['relayActivityAgeMs'], 0)
        self.assertIn('手机中转', out['reply'])
        self.assertNotIn('没有板端心跳', out['reply'])
        self.assertNotIn('可以执行', out['reply'])
        self.assertEqual(self.conversation.started, [])

    def test_old_success_heartbeat_cannot_make_expired_relay_executable(self):
        self.now += 16
        with patch.object(events, 'latest_exec', return_value=0, create=True) as legacy:
            out = self.status()
            self.assertNotIn('可以执行', out['reply'])
            legacy.assert_not_called()
        self.assertEqual(out['diagnostics']['relayState'], 'stale')
        self.assertEqual(out['diagnostics']['relayActivityAgeMs'], 16000)
        self.assertNotIn('可以执行', out['reply'])
        self.assertEqual(self.conversation.started, [])

    def test_share_authorization_is_device_scoped_and_does_not_prune(self):
        cases = ({}, {'expired': (100, self.device, 'usb-screen')},
                 {'other': (400, 'another-board', 'usb-screen')},
                 {'valid': (400, self.device, 'usb-screen')})
        for tickets in cases:
            with self.subTest(tickets=list(tickets)):
                self.authority.tickets = tickets.copy()
                before = self.snapshot_state()
                out = self.status()
                self.assertEqual(out['diagnostics']['deviceShareAuthorized'], 'valid' in tickets)
                self.assertEqual(self.snapshot_state(), before)

    def test_recent_lease_requires_matching_turn_and_session_and_expires_at_boundary(self):
        turn = self.gateway.turns[self.device]
        for key, value in (('owner', 'another-owner'), ('nonce', '34' * 16),
                           ('session', '56' * 8)):
            with self.subTest(mismatch=key):
                old = turn[key]
                turn[key] = value
                out = self.gateway.diagnostic_snapshot(self.device)
                self.assertEqual(out, {'relayState': 'unknown', 'relayActivityAgeMs': None})
                turn[key] = old
        for elapsed, state in ((0, 'recent'), (15, 'recent'), (15.001, 'stale')):
            self.now = 100 + elapsed
            out = self.gateway.diagnostic_snapshot(self.device)
            self.assertEqual(out['relayState'], state)
            self.assertEqual(out['relayActivityAgeMs'], round(elapsed * 1000))
        self.assertEqual(self.gateway.diagnostic_snapshot('another-board'),
                         {'relayState': 'unknown', 'relayActivityAgeMs': None})

    def test_activity_can_come_from_ack_not_only_poll(self):
        action = self.relay.offer(self.device, 6, [0] * 5)
        packet = self.relay.poll(self.device, self.owner[1], NONCE)
        self.now += 14
        self.relay.ack(self.device, self.owner[1], NONCE, action,
                       receipt(packet['seq'], 6, 7, 1))
        self.now += 2
        out = self.gateway.diagnostic_snapshot(self.device)
        self.assertEqual(out, {'relayState': 'recent', 'relayActivityAgeMs': 2000})

    def test_snapshot_does_not_issue_reconcile_renew_or_disclose_private_state(self):
        self.relay.offer(self.device, 6, [0] * 5)
        job = self.conversation.mailbox.create(self.device, 'c' * 16, 1)
        self.conversation.mailbox.offer(job, {'op': 'hid_home'})
        self.authority.tickets['expired-private-ticket'] = (99, self.device, 'usb-screen')
        for elapsed in (0, 16):
            self.now = 100 + elapsed
            before = self.snapshot_state()
            with ExitStack() as guards:
                for obj, name in ((self.gateway, 'poll'), (self.gateway, 'direct_blocked'),
                                  (self.gateway, 'usb_window'), (self.relay, '_session'),
                                  (self.relay, 'poll'), (self.relay, 'offer'),
                                  (self.authority, '_prune'), (relay_http, 'gateway')):
                    guards.enter_context(patch.object(obj, name, side_effect=AssertionError('mutating read: ' + name)))
                out = self.status()
            self.assertEqual(self.snapshot_state(), before)
            self.assertEqual(set(out['diagnostics']),
                             {'deviceShareAuthorized', 'relayState', 'relayActivityAgeMs', 'boardDirectState'})
            wire = json.dumps(out, ensure_ascii=False)
            for private in ('private-owner', NONCE, 'private-capture-ticket',
                            'expired-private-ticket', job.command['id'], job.session):
                self.assertNotIn(private, wire)

    def test_no_existing_gateway_is_observed_without_creating_one(self):
        with patch.object(relay_http, 'GATEWAY', None), patch.object(
                relay_http, 'gateway', side_effect=AssertionError('factory cannot be used')):
            out = self.status()
        self.assertEqual(out['diagnostics']['relayState'], 'unknown')
        self.assertEqual(out['diagnostics']['relayActivityAgeMs'], None)

    def test_state_change_during_snapshot_discards_queued_diagnostics(self):
        real = self.gateway.diagnostic_snapshot
        def stop_during_snapshot(device):
            self.remote.stop(self.owner)
            return real(device)
        with patch.object(self.gateway, 'diagnostic_snapshot', side_effect=stop_during_snapshot):
            out = self.status()
        self.assertEqual(out['state'], 'stopped')
        self.assertNotIn('diagnostics', out)
        self.assertNotIn('手机中转', out['reply'])

    def test_real_claim_during_snapshot_returns_running_without_queued_diagnostics(self):
        real = self.gateway.diagnostic_snapshot
        def claim_during_snapshot(device):
            lease = self.remote.claim(device, 'd' * 16, 1, False, 'absolute-v1')['lease']
            claim = self.remote.claim(device, 'd' * 16, 1, True, 'absolute-v1', lease)
            self.assertEqual(claim['op'], 'start')
            return real(device)
        with patch.object(self.gateway, 'diagnostic_snapshot', side_effect=claim_during_snapshot):
            out = self.status()
        self.assertEqual(out['state'], 'running')
        self.assertNotIn('diagnostics', out)
        self.assertEqual(len(self.conversation.started), 1)

    def test_capture_and_gateway_snapshots_have_separate_lock_scopes(self):
        def capture_clock():
            self.assertFalse(self.remote.lock._is_owned())
            self.assertFalse(self.gateway.lock._is_owned())
            self.assertFalse(self.relay.lock._is_owned())
            return self.now
        def relay_clock():
            self.assertFalse(self.remote.lock._is_owned())
            self.assertTrue(self.gateway.lock._is_owned())
            self.assertTrue(self.relay.lock._is_owned())
            acquired = self.authority.lock.acquire(timeout=.2)
            self.assertTrue(acquired)
            if acquired:
                self.authority.lock.release()
            return self.now
        with patch.object(self.authority, 'clock', side_effect=capture_clock) as capture, \
                patch.object(self.relay, 'clock', side_effect=relay_clock) as relay:
            out = self.status()
        capture.assert_called_once_with()
        relay.assert_called_once_with()
        self.assertEqual(out['diagnostics']['relayState'], 'recent')

    def test_latest_task_change_during_snapshot_discards_old_diagnostics(self):
        real = self.gateway.diagnostic_snapshot
        newer = []
        def replace_latest(device):
            newer.append(self.remote.prepare(self.owner, '打开设置')['task_id'])
            return real(device)
        with patch.object(self.gateway, 'diagnostic_snapshot', side_effect=replace_latest):
            out = self.remote.status(self.owner)
        self.assertEqual(out['task_id'], newer[0])
        self.assertEqual(out['state'], 'pending')
        self.assertNotIn('diagnostics', out)

    def test_queue_expiry_during_snapshot_discards_old_diagnostics(self):
        real = self.gateway.diagnostic_snapshot
        def expire_during_snapshot(device):
            self.now += 61
            return real(device)
        with patch.object(self.gateway, 'diagnostic_snapshot', side_effect=expire_during_snapshot):
            out = self.status()
        self.assertEqual(out['state'], 'expired')
        self.assertNotIn('diagnostics', out)

    def test_snapshot_does_not_hold_remote_or_authority_lock_while_waiting_for_gateway(self):
        ready = threading.Event()
        inspect = threading.Event()
        remote_acquired = []
        errors = []
        answers = []
        def gateway_worker():
            try:
                with self.gateway.lock:
                    ready.set()
                    if not inspect.wait(2):
                        raise AssertionError('status did not reach gateway snapshot')
                    acquired = self.remote.lock.acquire(timeout=.5)
                    remote_acquired.append(acquired)
                    if acquired:
                        self.remote.lock.release()
            except Exception as error:
                errors.append(error)
        def query():
            try:
                answers.append(self.status())
            except Exception as error:
                errors.append(error)
        real = self.gateway.diagnostic_snapshot
        def snapshot(device):
            self.assertFalse(self.remote.lock._is_owned())
            acquired = self.authority.lock.acquire(timeout=.2)
            self.assertTrue(acquired, 'AUTHORITY must be released before Gateway')
            if acquired:
                self.authority.lock.release()
            inspect.set()
            return real(device)
        worker = threading.Thread(target=gateway_worker, daemon=True)
        reader = threading.Thread(target=query, daemon=True)
        with patch.object(self.gateway, 'diagnostic_snapshot', side_effect=snapshot):
            worker.start()
            self.assertTrue(ready.wait(2))
            reader.start()
            worker.join(3)
            reader.join(3)
        self.assertFalse(worker.is_alive() or reader.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(remote_acquired, [True])
        self.assertEqual(answers[0]['state'], 'queued')

    def test_unauthorized_owner_does_not_read_device_diagnostics(self):
        with patch.object(self.gateway, 'diagnostic_snapshot', side_effect=AssertionError('unauthorized read')):
            with self.assertRaises(ValueError):
                self.remote.status(('telegram', 'another-owner', 'other-chat', self.device), self.ident)


if __name__ == '__main__':
    unittest.main()
