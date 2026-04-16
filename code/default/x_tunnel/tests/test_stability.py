from unittest import TestCase
from unittest import mock
import os
import sys
import threading
import time
import types

current_path = os.path.dirname(os.path.abspath(__file__))
default_path = os.path.abspath(os.path.join(current_path, os.path.pardir, os.path.pardir))
root_path = os.path.abspath(os.path.join(default_path, os.path.pardir, os.path.pardir))

noarch_lib = os.path.abspath(os.path.join(default_path, 'lib', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.append(noarch_lib)
if default_path not in sys.path:
    sys.path.append(default_path)
if root_path not in sys.path:
    sys.path.append(root_path)

from x_tunnel.local import front_dispatcher
from x_tunnel.local import global_var as g
from x_tunnel.local import check_local_network
from x_tunnel.local import proxy_session
from x_tunnel.local import web_control


class ConfigStub(object):
    max_payload = 1024
    send_delay = 10
    ack_delay = 10
    resend_timeout = 1000
    enable_tls_relay = False
    upload_logs = False
    concurent_thread_num = 0
    send_timeout_retry = 1
    min_on_road = 0
    show_debug = False
    enable_cloudflare = False
    enable_cloudfront = False
    enable_seley = False
    enable_direct = True
    login_account = "test@example.com"
    login_password = "password_hash"
    server_host = ""
    server_port = 443
    api_server = "api.xx-net.test"

    def save(self):
        pass

    def load(self):
        pass


class FakeFront(object):
    def __init__(self, name):
        self.name = name
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1

    def get_dispatcher(self, host=None):
        return None


class ReadyDispatcher(object):
    def __init__(self):
        self.available = False
        self.checked = threading.Event()

    def get_score(self):
        self.checked.set()
        if self.available:
            return 100
        return 0


class ReadyFront(FakeFront):
    def __init__(self, name):
        super().__init__(name)
        self.dispatcher = ReadyDispatcher()
        self.config = types.SimpleNamespace(show_state_debug=False)

    def get_dispatcher(self, host=None):
        return self.dispatcher


class FakeThread(object):
    def __init__(self, target=None, args=(), kwargs=None, name=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.name = name
        self.daemon = False
        self.started = False
        self.join_called = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started and not self.join_called

    def join(self, timeout=None):
        self.join_called = True


class FakeThreadFactory(object):
    def __init__(self):
        self.created_threads = []

    def __call__(self, *args, **kwargs):
        thread = FakeThread(*args, **kwargs)
        self.created_threads.append(thread)
        return thread


class SessionStub(object):
    traffic_upload = 1
    traffic_download = 2

    def __init__(self):
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1


class TestControlHandler(web_control.ControlHandler):
    def __init__(self, path="/info"):
        super().__init__(("127.0.0.1", 0), {}, "GET", path, None, None)
        self.postvars = {}
        self.json_responses = []

    def response_json(self, res_arr, headers=b""):
        self.json_responses.append(res_arr)
        return res_arr


class ProxySessionLifecycleTest(TestCase):
    def setUp(self):
        self.old_config = g.config
        self.old_running = g.running
        self.sessions = []
        g.config = ConfigStub()
        g.running = True

    def tearDown(self):
        for session in self.sessions:
            session.stop()
        g.config = self.old_config
        g.running = self.old_running

    def test_timeout_checker_starts_with_session_and_stops_on_stop(self):
        session = proxy_session.ProxySession()
        self.sessions.append(session)

        self.assertIsNone(session.timeout_check_th)

        with mock.patch.object(proxy_session.ProxySession, "login_session", return_value=True):
            self.assertTrue(session.start())

        self.assertIsNotNone(session.timeout_check_th)
        self.assertTrue(session.timeout_check_th.is_alive())

        session.stop()
        deadline = time.time() + 3
        while session.timeout_check_th.is_alive() and time.time() < deadline:
            time.sleep(0.05)

        self.assertFalse(session.timeout_check_th.is_alive())

    def test_timeout_checker_does_not_duplicate_across_restart(self):
        session = proxy_session.ProxySession()
        self.sessions.append(session)

        with mock.patch.object(proxy_session.ProxySession, "login_session", return_value=True):
            self.assertTrue(session.start())

        first_thread = session.timeout_check_th
        self.assertTrue(first_thread.is_alive())

        session.stop()
        deadline = time.time() + 3
        while first_thread.is_alive() and time.time() < deadline:
            time.sleep(0.05)

        with mock.patch.object(proxy_session.ProxySession, "login_session", return_value=True):
            self.assertTrue(session.start())

        second_thread = session.timeout_check_th
        self.assertIsNot(first_thread, second_thread)
        self.assertTrue(second_thread.is_alive())
        self.assertFalse(first_thread.is_alive())


class FrontDispatcherInitTest(TestCase):
    def setUp(self):
        self.old_config = g.config
        self.old_running = g.running
        self.old_direct_front = sys.modules.get("x_tunnel.local.direct_front")
        g.config = ConfigStub()
        g.running = True
        self.fake_front = FakeFront("direct_front")
        sys.modules["x_tunnel.local.direct_front"] = self.fake_front
        front_dispatcher.stop()

    def tearDown(self):
        front_dispatcher.stop()
        if self.old_direct_front is None:
            sys.modules.pop("x_tunnel.local.direct_front", None)
        else:
            sys.modules["x_tunnel.local.direct_front"] = self.old_direct_front
        g.config = self.old_config
        g.running = self.old_running

    def test_init_is_idempotent(self):
        thread_factory = FakeThreadFactory()

        with mock.patch.object(front_dispatcher.threading, "Thread", side_effect=thread_factory):
            front_dispatcher.init()
            front_dispatcher.init()

        self.assertEqual(len(front_dispatcher.all_fronts), 1)
        self.assertEqual(len(front_dispatcher.session_fronts), 1)
        self.assertEqual(len(front_dispatcher.light_fronts), 1)
        self.assertEqual(self.fake_front.start_calls, 1)
        self.assertEqual(len(thread_factory.created_threads), 1)

        front_dispatcher.stop()
        self.assertEqual(self.fake_front.stop_calls, 1)
        self.assertEqual(len(front_dispatcher.all_fronts), 0)

    def test_init_after_stop_starts_front_again(self):
        thread_factory = FakeThreadFactory()

        with mock.patch.object(front_dispatcher.threading, "Thread", side_effect=thread_factory):
            front_dispatcher.init()
            front_dispatcher.stop()
            front_dispatcher.init()

        self.assertEqual(self.fake_front.start_calls, 2)
        self.assertEqual(len(front_dispatcher.all_fronts), 1)
        self.assertEqual(len(thread_factory.created_threads), 2)


class FrontDispatcherPerformanceTest(TestCase):
    def setUp(self):
        self.old_config = g.config
        self.old_stat = getattr(g, "stat", None)
        g.config = ConfigStub()
        g.stat = {"timeout_roundtrip": 0}
        front_dispatcher.stop()

    def tearDown(self):
        front_dispatcher.stop()
        g.config = self.old_config
        g.stat = self.old_stat

    def test_get_front_waits_on_notification_instead_of_busy_sleep(self):
        ready_front = ReadyFront("ready_front")
        front_dispatcher.session_fronts[:] = [ready_front]

        real_sleep = time.sleep

        def make_front_ready():
            self.assertTrue(ready_front.dispatcher.checked.wait(1))
            ready_front.dispatcher.available = True
            front_dispatcher.notify_front_ready()

        notifier = threading.Thread(target=make_front_ready)
        notifier.daemon = True
        notifier.start()

        with mock.patch.object(front_dispatcher.time, "sleep", side_effect=AssertionError("busy wait")):
            front = front_dispatcher.get_front("example.com", 0.5)

        notifier.join(1)
        self.assertIs(front, ready_front)


class BackgroundTaskTest(TestCase):
    def tearDown(self):
        tasks = list(web_control._background_tasks.values())
        for thread in tasks:
            thread.join(1)
        web_control._background_tasks.clear()

    def test_start_background_task_deduplicates_running_task(self):
        entered = threading.Event()
        release = threading.Event()
        call_count = []

        def task():
            call_count.append(1)
            entered.set()
            release.wait(2)

        self.assertTrue(web_control._start_background_task("quota_update", task))
        self.assertTrue(entered.wait(1))
        self.assertFalse(web_control._start_background_task("quota_update", task))

        release.set()
        thread = web_control._background_tasks.get("quota_update")
        if thread:
            thread.join(1)

        self.assertEqual(len(call_count), 1)
        self.assertNotIn("quota_update", web_control._background_tasks)

    def test_start_background_task_can_run_again_after_completion(self):
        call_count = []

        def task():
            call_count.append(1)

        self.assertTrue(web_control._start_background_task("session_reset", task))
        first_thread = web_control._background_tasks["session_reset"]
        first_thread.join(1)

        self.assertTrue(web_control._start_background_task("session_reset", task))
        second_thread = web_control._background_tasks["session_reset"]
        second_thread.join(1)

        self.assertEqual(len(call_count), 2)


class CheckLocalNetworkTest(TestCase):
    def test_trigger_check_network_deduplicates_pending_worker(self):
        checker = check_local_network.CheckNetwork("IPv4")
        checker.last_check_time = 0
        checker.network_stat = "Fail"
        thread_factory = FakeThreadFactory()

        with mock.patch.object(check_local_network.threading, "Thread", side_effect=thread_factory):
            checker.triger_check_network()
            checker.triger_check_network()

        self.assertEqual(len(thread_factory.created_threads), 1)
        self.assertEqual(checker._checking_num, 1)


class WebControlHandlerTest(TestCase):
    def setUp(self):
        self.old_config = g.config
        self.old_session = g.session
        self.old_last_refresh_time = g.last_refresh_time
        self.old_last_api_error = g.last_api_error
        self.old_selectable = g.selectable
        self.old_promoter = g.promoter
        self.old_plans = g.plans
        self.old_balance = g.balance
        self.old_openai_balance = g.openai_balance
        self.old_quota = g.quota
        self.old_quota_list = g.quota_list
        self.old_center_login_process = g.center_login_process

        g.config = ConfigStub()
        g.session = SessionStub()
        g.last_refresh_time = 0
        g.last_api_error = ""
        g.selectable = [("server-a", "server-a")]
        g.promoter = "promoter"
        g.plans = {"plan-a": {"desc": "test"}}
        g.balance = 10
        g.openai_balance = 1
        g.quota = 2
        g.quota_list = {}
        g.center_login_process = False

    def tearDown(self):
        g.config = self.old_config
        g.session = self.old_session
        g.last_refresh_time = self.old_last_refresh_time
        g.last_api_error = self.old_last_api_error
        g.selectable = self.old_selectable
        g.promoter = self.old_promoter
        g.plans = self.old_plans
        g.balance = self.old_balance
        g.openai_balance = self.old_openai_balance
        g.quota = self.old_quota
        g.quota_list = self.old_quota_list
        g.center_login_process = self.old_center_login_process

    def test_req_info_handler_force_triggers_background_refresh(self):
        handler = TestControlHandler("/info?force=1")

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_info_handler()

        self.assertEqual(result["res"], "login_process")
        start_task.assert_called_once_with(
            "info__request_balance",
            proxy_session.request_balance,
            args=(None, None, False, False)
        )

    def test_req_info_handler_force_overrides_recent_cache(self):
        handler = TestControlHandler("/info?force=1")
        g.last_refresh_time = time.time()

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_info_handler()

        self.assertEqual(result["res"], "login_process")
        start_task.assert_called_once_with(
            "info__request_balance",
            proxy_session.request_balance,
            args=(None, None, False, False)
        )

    def test_req_config_handler_set_server_triggers_session_reset(self):
        handler = TestControlHandler("/config?cmd=set")
        handler.postvars = {"server": "server-a"}

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_config_handler()

        self.assertEqual(result["res"], "success")
        self.assertEqual(g.config.server_host, "server-a")
        start_task.assert_called_once_with("session_reset", g.session.reset)

    def test_req_config_handler_same_server_skips_session_reset(self):
        handler = TestControlHandler("/config?cmd=set")
        handler.postvars = {"server": "server-a"}
        g.config.server_host = "server-a"

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_config_handler()

        self.assertEqual(result["res"], "success")
        start_task.assert_not_called()

    def test_req_info_handler_cached_status_skips_background_refresh(self):
        handler = TestControlHandler("/info")
        g.last_refresh_time = time.time()

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            handler.req_info_handler()

        self.assertEqual(handler.json_responses[-1]["res"], "success")
        start_task.assert_not_called()

    def test_req_info_handler_status_error_after_window_triggers_refresh(self):
        handler = TestControlHandler("/info")
        g.last_refresh_time = time.time() - 31
        g.last_api_error = "status:502"

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_info_handler()

        self.assertEqual(result["res"], "login_process")
        start_task.assert_called_once_with(
            "info__request_balance",
            proxy_session.request_balance,
            args=(None, None, False, False)
        )

    def test_req_reset_password_failure_triggers_quota_update(self):
        handler = TestControlHandler("/reset_password")
        handler.postvars = {
            "username": "user@example.com",
            "stage": "request_reset_password",
            "code": ""
        }

        with mock.patch.object(proxy_session, "call_api", return_value=(False, "api fail")), \
                mock.patch.object(proxy_session, "get_app_name", return_value="x_tunnel"), \
                mock.patch.object(web_control, "get_lang", return_value="en"), \
                mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_reset_password()

        self.assertEqual(result["res"], "fail")
        self.assertEqual(result["reason"], "api fail")
        start_task.assert_called_once_with("update_quota_loop", proxy_session.update_quota_loop)

    def test_req_order_handler_failure_triggers_quota_update(self):
        handler = TestControlHandler("/order")
        handler.postvars = {"product": "x_tunnel", "plan": "plan-a"}

        with mock.patch.object(proxy_session, "call_api", return_value=(False, "order fail")), \
                mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_order_handler()

        self.assertEqual(result["res"], "fail")
        self.assertEqual(result["reason"], "order fail")
        start_task.assert_called_once_with("update_quota_loop", proxy_session.update_quota_loop)

    def test_req_config_handler_auto_switch_triggers_session_reset_once(self):
        handler = TestControlHandler("/config?cmd=set")
        handler.postvars = {"server": "auto"}
        g.config.server_host = "server-a"

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_config_handler()

        self.assertEqual(result["res"], "success")
        self.assertEqual(g.config.server_host, "")
        start_task.assert_called_once_with("session_reset", g.session.reset)

    def test_req_config_handler_recovers_after_invalid_server(self):
        handler = TestControlHandler("/config?cmd=set")
        handler.postvars = {"server": "server-bad"}

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_config_handler()

        self.assertEqual(result["res"], "fail")
        self.assertEqual(result["reason"], "server not available")
        start_task.assert_not_called()

        handler.postvars = {"server": "auto"}
        g.config.server_host = "server-a"

        with mock.patch.object(web_control, "_start_background_task", return_value=True) as start_task:
            result = handler.req_config_handler()

        self.assertEqual(result["res"], "success")
        self.assertEqual(g.config.server_host, "")
        start_task.assert_called_once_with("session_reset", g.session.reset)
