"""Offline navigation boundaries around slow visual reads, using real mailboxes.

Only provider routing and the HTTP boundary are substituted. Frames, turn
expiry, cancellation, receipt state and navigation fences use production code.
"""
import base64
import io
import json
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from display_service import general_vision
from display_service.dialogue import Mailbox
from display_service.general_nav import GeneralNavigator
from display_service.skill_engine import SkillStore
from test_wechat_nav import frame


class VisionRetryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Do not select optional live judges or write screenshot evidence.
        env = patch.dict('os.environ', {'EPAPER_NAV_JUDGE': '', 'EPAPER_NAV_EVIDENCE_DIR': ''})
        env.start()
        self.addCleanup(env.stop)
        self.cfg = {'baseUrl': 'https://synthetic.invalid/v1', 'apiKey': 'synthetic-only'}

    def scenario(self):
        self.now = 100.0
        self.mailbox = Mailbox(clock=lambda: self.now)
        self.job = self.mailbox.create('synthetic-vision-boundary', 'a' * 16, 1)
        self.job.pointer_protocol = 'absolute-v1'
        self.job.screen_session = 'synthetic-capture'
        # A previously acknowledged action must not be issued again by a read retry.
        self.mailbox.offer(self.job, {'op': 'hid_home'})
        command = self.mailbox.poll(self.job.device, self.job.session, self.job.sequence)
        self.mailbox.ack(self.job.device, self.job.session, self.job.sequence,
                         command['id'], True, 'HID_HOME_REPORT_SENT')
        self.receipt = dict(self.job.last_receipt)
        self.job.fenced = True
        self.emit(frame(0))
        self.nav = GeneralNavigator(self.mailbox, SkillStore(Path(self.tmp.name)),
                                    vision=general_vision.observe, frame_timeout=.5)
        self.initial = self.nav._frame(self.job)

    def emit(self,raw):
        j = self.job
        self.mailbox.ingest_video(j.device, j.session, j.sequence, j.video_sequence + 1,
                                  raw, 'jpeg', expected_barrier=j.video_barrier,
                                  source='user-consented-app-screen')

    @staticmethod
    def response():
        observation = dict(coordinate_system='pixels', safe=True, complete=False,
                           screen='应用列表', action='click', target_label='相机',
                           bounds=[20, 100, 80, 160])
        return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop',
                             'message': {'content': json.dumps(observation)}}]}).encode())

    def observe(self):
        return self.nav._observe_frame(self.job, *self.initial, '打开相机')

    def network(self,opener):
        guards = ExitStack()
        route = guards.enter_context(patch.object(general_vision, 'vision_route',
            side_effect=[('opencode-go', 'mimo-v2.6-flash', dict(self.cfg)),
                         ('xiaomi', 'unexpected-model', {'baseUrl': 'https://unexpected.invalid',
                                                       'apiKey': 'unexpected-key'})]))
        net = guards.enter_context(patch.object(general_vision, '_open_vision', side_effect=opener))
        return guards, route, net

    def assert_no_new_action(self):
        self.assertIsNone(self.job.command)
        self.assertEqual(self.job.last_receipt, self.receipt)
        self.assertFalse(self.job.navigation_verified)
        self.assertEqual(self.mailbox.high, {(self.job.device, self.job.session): 1})
        if not self.job.cancelled:
            self.assertEqual(self.mailbox.poll(self.job.device, self.job.session,
                                              self.job.sequence)['op'], 'wait')

    def test_retry_uses_new_frame_and_original_route_without_replaying_hid(self):
        self.scenario()
        requests = []
        configs = []
        real_headers = general_vision.request_headers
        def headers(cfg):
            configs.append(dict(cfg))
            return real_headers(cfg)
        def open_request(request,provider,timeout):
            payload = json.loads(request.data)
            encoded = payload['messages'][1]['content'][1]['image_url']['url'].split(',', 1)[1]
            requests.append((provider, payload['model'], request.full_url,
                             request.get_header('Authorization'), base64.b64decode(encoded)))
            if len(requests) == 1:
                self.emit(frame(1))
                raise TimeoutError('synthetic slow response')
            return self.response()
        guards, route, net = self.network(open_request)
        with guards, patch.object(general_vision, 'request_headers', side_effect=headers):
            raw, seq, _, observation = self.observe()
        self.assertEqual(net.call_count, 2)
        self.assertEqual(route.call_count, 1)
        self.assertEqual(configs, [self.cfg, self.cfg])
        self.assertEqual(requests[0][:4], requests[1][:4])
        self.assertEqual(requests[0][4], self.initial[0])
        self.assertEqual(requests[1][4], raw)
        self.assertNotEqual(requests[0][4], requests[1][4])
        self.assertGreater(seq, self.initial[1])
        self.assertEqual(observation['action'], 'click')
        self.assert_no_new_action()

    def test_second_transport_failure_has_no_third_request_or_hid_replay(self):
        self.scenario()
        def open_request(*args, **kwargs):
            self.emit(frame(1))  # A third attempt would have a usable newer frame.
            raise TimeoutError('synthetic slow response')
        guards, route, net = self.network(open_request)
        with guards, self.assertRaises(general_vision.VisionTransportError):
            self.observe()
        self.assertEqual(net.call_count, 2)
        self.assertEqual(route.call_count, 1)
        self.assert_no_new_action()

    def test_missing_new_frame_prevents_retry_until_stop_cancels_wait(self):
        self.scenario()
        requested = threading.Event()
        finished = threading.Event()
        errors = []
        def open_request(*args, **kwargs):
            requested.set()
            raise TimeoutError('synthetic slow response')
        def query():
            try:self.observe()
            except Exception as error:errors.append(error)
            finally:finished.set()
        guards, _, net = self.network(open_request)
        thread = threading.Thread(target=query, daemon=True)
        with guards:
            thread.start()
            try:
                self.assertTrue(requested.wait(2))
                self.assertFalse(finished.wait(.05), 'the old frame must not satisfy retry')
                self.assertEqual(net.call_count, 1)
            finally:
                self.mailbox.cancel(self.job.device)
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(net.call_count, 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertIn('cancelled or expired', str(errors[0]))
        self.assert_no_new_action()

    def late_success(self,change,*,on_retry=False):
        self.scenario()
        waiting = threading.Event()
        release = threading.Event()
        returned = []
        errors = []
        calls = []
        def open_request(*args, **kwargs):
            calls.append(True)
            if on_retry and len(calls) == 1:
                self.emit(frame(1))
                raise TimeoutError('synthetic first attempt timeout')
            waiting.set()
            if not release.wait(2):raise AssertionError('test did not release visual response')
            return self.response()
        def query():
            try:
                result = self.observe()
                returned.append(result)
                # A wrongly accepted result would reach the real action/frame fence.
                self.nav._action(self.job, self.nav._command(result[3], '打开相机'), result[2])
            except Exception as error:errors.append(error)
        guards, _, net = self.network(open_request)
        thread = threading.Thread(target=query, daemon=True)
        with guards:
            thread.start()
            try:
                self.assertTrue(waiting.wait(2))
                change()
            finally:
                release.set()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(net.call_count, 2 if on_retry else 1)
        self.assertEqual(returned, [], 'a cancelled or superseded read must not return coordinates')
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assert_no_new_action()
        return errors[0]

    def test_stop_during_either_request_discards_late_success(self):
        for retry in (False, True):
            with self.subTest(retry=retry):
                error = self.late_success(lambda: self.mailbox.cancel(self.job.device), on_retry=retry)
                self.assertIn('cancelled or expired', str(error))
                self.assertTrue(self.job.cancelled)

    def test_idle_expiry_during_either_request_discards_late_success(self):
        def expire():
            with self.mailbox.lock:self.now += 45.001
        for retry in (False, True):
            with self.subTest(retry=retry):
                error = self.late_success(expire, on_retry=retry)
                self.assertIn('cancelled or expired', str(error))
                self.assertTrue(self.job.cancelled)

    def test_total_lifetime_expiry_with_recent_polls_discards_late_success(self):
        def expire():
            # Real polling prevents idle expiry while the overall 180 s lifetime ends.
            for age in (40, 80, 120, 160):
                with self.mailbox.lock:self.now = self.job.created + age
                self.assertEqual(self.mailbox.poll(self.job.device, self.job.session,
                                                  self.job.sequence)['op'], 'wait')
            with self.mailbox.lock:self.now = self.job.created + 180.001
        for retry in (False, True):
            with self.subTest(retry=retry):
                error = self.late_success(expire, on_retry=retry)
                self.assertIn('cancelled or expired', str(error))
                self.assertTrue(self.job.cancelled)

    def test_capture_or_barrier_change_discards_late_success(self):
        for field in ('screen_session', 'video_barrier'):
            for retry in (False, True):
                with self.subTest(field=field,retry=retry):
                    def change():
                        with self.mailbox.lock:setattr(self.job, field, 'changed-capture-boundary')
                    error = self.late_success(change, on_retry=retry)
                    self.assertIn('画面会话已经改变', str(error))

    def test_capture_or_barrier_change_prevents_retry_after_failure(self):
        for field in ('screen_session', 'video_barrier'):
            with self.subTest(field=field):
                self.scenario()
                def open_request(*args, **kwargs):
                    with self.mailbox.lock:setattr(self.job, field, 'changed-capture-boundary')
                    raise TimeoutError('synthetic slow response')
                guards, _, net = self.network(open_request)
                with guards, self.assertRaisesRegex(ValueError, '画面会话已经改变'):
                    self.observe()
                self.assertEqual(net.call_count, 1)
                self.assert_no_new_action()

    def test_different_retry_frame_dimensions_are_rejected(self):
        self.scenario()
        def open_request(*args, **kwargs):
            with Image.open(io.BytesIO(frame(1))) as image:
                output = io.BytesIO()
                image.resize((300, 600)).save(output, format='JPEG')
            self.emit(output.getvalue())
            raise TimeoutError('synthetic slow response')
        guards, _, net = self.network(open_request)
        with guards, self.assertRaisesRegex(ValueError, '共享画面尺寸改变'):
            self.observe()
        self.assertEqual(net.call_count, 1)
        self.assert_no_new_action()


if __name__ == '__main__':
    unittest.main()
