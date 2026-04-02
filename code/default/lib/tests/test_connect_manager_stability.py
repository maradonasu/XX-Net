import os
import sys
import threading
import time
import unittest
from unittest import mock

current_path = os.path.dirname(os.path.abspath(__file__))
default_path = os.path.abspath(os.path.join(current_path, os.path.pardir))
root_path = os.path.abspath(os.path.join(default_path, os.path.pardir, os.path.pardir))

noarch_lib = os.path.abspath(os.path.join(default_path, 'noarch'))
if noarch_lib not in sys.path:
    sys.path.append(noarch_lib)
if default_path not in sys.path:
    sys.path.append(default_path)
if root_path not in sys.path:
    sys.path.append(root_path)

from front_base import connect_manager


class ConfigStub(object):
    show_state_debug = False
    connection_pool_min = 0
    https_keep_alive = 10
    https_connection_pool_min = 0
    https_connection_pool_max = 10
    https_max_connect_thread = 2
    connect_create_interval = 0


class LoggerStub(object):
    name = "test"

    def debug(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def warn(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class IPManagerStub(object):
    def __init__(self):
        self.fail_reports = []
        self.close_reports = []

    def ssl_closed(self, *args, **kwargs):
        pass

    def update_ip(self, *args, **kwargs):
        pass

    def report_connect_fail(self, *args, **kwargs):
        self.fail_reports.append((args, kwargs))

    def report_connect_closed(self, *args, **kwargs):
        self.close_reports.append((args, kwargs))


class ConnectCreatorStub(object):
    def __init__(self):
        self.calls = []

    def connect_ssl(self, ip_str, sni, host, close_cb=None):
        self.calls.append((ip_str, sni, host, close_cb))
        ssl_sock = mock.Mock()
        ssl_sock.handshake_time = 123
        ssl_sock.h2 = False
        ssl_sock.sni = sni
        ssl_sock.host = host
        ssl_sock.last_use_time = 0
        return ssl_sock


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
        self.created = []

    def __call__(self, *args, **kwargs):
        thread = FakeThread(*args, **kwargs)
        self.created.append(thread)
        return thread


class ClosableSock(object):
    def __init__(self):
        self.closed = False
        self.last_use_time = 0
        self.ip_str = "1.1.1.1:443"
        self.sni = "example.com"

    def close(self):
        self.closed = True


class BrokenSock(object):
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ObservableConnectPool(connect_manager.ConnectPool):
    def __init__(self):
        super(ObservableConnectPool, self).__init__()
        self.wait_started = threading.Event()

    def get(self, block=True, timeout=None):
        if block:
            self.wait_started.set()
        return super(ObservableConnectPool, self).get(block=block, timeout=timeout)


class ConnectManagerStabilityTest(unittest.TestCase):
    def test_get_ssl_connection_zero_timeout_returns_none(self):
        creator = ConnectCreatorStub()
        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=ConfigStub(),
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )

        with mock.patch.object(manager, "_create_more_connection") as create_more_connection:
            result = manager.get_ssl_connection(timeout=0)

        self.assertIsNone(result)
        self.assertEqual(manager._connection_waiting_num, 0)
        self.assertEqual(create_more_connection.call_count, 0)

    def test_get_ssl_connection_zero_timeout_skips_wakeup_when_pool_empty(self):
        creator = ConnectCreatorStub()
        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=ConfigStub(),
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )

        with mock.patch.object(manager, "_create_more_connection") as create_more_connection:
            result = manager.get_ssl_connection(timeout=-1)

        self.assertIsNone(result)
        self.assertEqual(create_more_connection.call_count, 0)
        self.assertEqual(manager._connection_waiting_num, 0)

    def test_get_ssl_connection_uses_remaining_timeout_for_pool_wait(self):
        creator = ConnectCreatorStub()
        thread_factory = FakeThreadFactory()

        with mock.patch.object(connect_manager.threading, "Thread", side_effect=thread_factory):
            manager = connect_manager.ConnectManager(
                logger=LoggerStub(),
                config=ConfigStub(),
                connect_creator=creator,
                ip_manager=IPManagerStub(),
                check_local_network=mock.Mock()
            )

        pool_get_calls = []

        def fake_get(block=True, timeout=None):
            pool_get_calls.append((block, timeout))
            if not block:
                return None
            raise RuntimeError("stop after wait")

        manager.new_conn_pool = mock.Mock()
        manager.new_conn_pool.get.side_effect = fake_get

        with mock.patch.object(manager, "_create_more_connection"):
            with self.assertRaises(RuntimeError):
                manager.get_ssl_connection(timeout=0.2)

        self.assertEqual(pool_get_calls[0], (False, None))
        self.assertLessEqual(pool_get_calls[1][1], 0.2)

    def test_stop_wakes_waiting_get_ssl_connection(self):
        creator = ConnectCreatorStub()
        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=ConfigStub(),
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )

        result_holder = []

        def wait_connection():
            with mock.patch.object(manager, "_create_more_connection"):
                result_holder.append(manager.get_ssl_connection(timeout=1))

        waiter = connect_manager.threading.Thread(target=wait_connection, name="wait_ssl_connection")
        waiter.daemon = True
        waiter.start()

        deadline = time.time() + 1
        while manager._connection_waiting_num == 0 and time.time() < deadline:
            time.sleep(0.01)

        manager.stop()
        waiter.join(0.3)

        self.assertFalse(waiter.is_alive())
        self.assertEqual(result_holder, [None])
        self.assertEqual(manager._connection_waiting_num, 0)

    def test_stop_wakes_multiple_waiting_get_ssl_connection(self):
        creator = ConnectCreatorStub()
        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=ConfigStub(),
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )

        result_holder = []
        started = connect_manager.threading.Event()

        def wait_connection():
            started.set()
            with mock.patch.object(manager, "_create_more_connection"):
                result_holder.append(manager.get_ssl_connection(timeout=5))

        waiters = []
        for i in range(2):
            waiter = connect_manager.threading.Thread(target=wait_connection, name="wait_ssl_connection_%d" % i)
            waiter.daemon = True
            waiter.start()
            waiters.append(waiter)

        self.assertTrue(started.wait(1))
        deadline = time.time() + 1
        while manager._connection_waiting_num < 2 and time.time() < deadline:
            time.sleep(0.01)

        manager.stop()

        for waiter in waiters:
            waiter.join(0.5)
            self.assertFalse(waiter.is_alive())

        self.assertEqual(len(result_holder), 2)
        self.assertTrue(all(result is None for result in result_holder))
        self.assertEqual(manager._connection_waiting_num, 0)

    def test_stop_releases_pool_waiters_promptly(self):
        creator = ConnectCreatorStub()
        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=ConfigStub(),
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )
        manager.new_conn_pool = ObservableConnectPool()

        result_holder = []

        def wait_connection():
            with mock.patch.object(manager, "_create_more_connection"):
                result_holder.append(manager.get_ssl_connection(timeout=3))

        waiter = connect_manager.threading.Thread(target=wait_connection, name="wait_ssl_connection_pool")
        waiter.daemon = True
        waiter.start()

        self.assertTrue(manager.new_conn_pool.wait_started.wait(1))
        manager.stop()
        waiter.join(0.5)

        self.assertFalse(waiter.is_alive())
        self.assertEqual(result_holder, [None])

    def test_init_normalizes_invalid_connect_thread_count(self):
        creator = ConnectCreatorStub()
        thread_factory = FakeThreadFactory()
        config = ConfigStub()
        config.https_max_connect_thread = 0

        with mock.patch.object(connect_manager.threading, "Thread", side_effect=thread_factory):
            manager = connect_manager.ConnectManager(
                logger=LoggerStub(),
                config=config,
                connect_creator=creator,
                ip_manager=IPManagerStub(),
                check_local_network=mock.Mock()
            )

        self.assertEqual(manager.config.https_max_connect_thread, 1)
        self.assertEqual(len(manager.connect_threads), 1)

    def test_init_caps_pool_min_to_pool_max(self):
        creator = ConnectCreatorStub()
        config = ConfigStub()
        config.connection_pool_min = 1
        config.https_connection_pool_min = 8
        config.https_connection_pool_max = 3

        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=config,
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )

        self.assertEqual(manager.config.https_connection_pool_min, 3)

    def test_init_normalizes_negative_pool_sizes(self):
        creator = ConnectCreatorStub()
        config = ConfigStub()
        config.https_connection_pool_min = -5
        config.https_connection_pool_max = -1

        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=config,
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )

        self.assertEqual(manager.config.https_connection_pool_min, 0)
        self.assertEqual(manager.config.https_connection_pool_max, 0)

    def test_init_normalizes_too_small_keep_alive(self):
        creator = ConnectCreatorStub()
        config = ConfigStub()
        config.https_keep_alive = 1

        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=config,
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )

        self.assertGreaterEqual(manager.config.https_keep_alive, 7)

    def test_keep_connection_daemon_notifies_workers_instead_of_connecting_directly(self):
        creator = ConnectCreatorStub()
        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=ConfigStub(),
            connect_creator=creator,
            ip_manager=IPManagerStub(),
            check_local_network=mock.Mock()
        )
        manager.config.connection_pool_min = 1
        manager.config.https_connection_pool_min = 1

        with mock.patch.object(manager, "_create_more_connection") as create_more_connection, \
                mock.patch.object(manager, "_connect_process") as connect_process:
            def stop_after_notify(*args, **kwargs):
                manager.running = False
            create_more_connection.side_effect = stop_after_notify
            connect_process.side_effect = stop_after_notify
            manager.keep_connection_daemon()

        self.assertEqual(create_more_connection.call_count, 1)
        self.assertEqual(connect_process.call_count, 0)

    def test_init_creates_fixed_connect_workers(self):
        creator = ConnectCreatorStub()
        thread_factory = FakeThreadFactory()

        with mock.patch.object(connect_manager.threading, "Thread", side_effect=thread_factory):
            manager = connect_manager.ConnectManager(
                logger=LoggerStub(),
                config=ConfigStub(),
                connect_creator=creator,
                ip_manager=IPManagerStub(),
                check_local_network=mock.Mock()
            )

        self.assertEqual(len(manager.connect_threads), ConfigStub.https_max_connect_thread)
        self.assertEqual(len(thread_factory.created), 1 + ConfigStub.https_max_connect_thread)
        self.assertFalse(hasattr(manager, "connecting_more_thread"))
        self.assertFalse(hasattr(manager, "thread_num"))

    def test_create_ssl_connection_does_not_spawn_helper_thread(self):
        creator = ConnectCreatorStub()
        thread_factory = FakeThreadFactory()

        with mock.patch.object(connect_manager.threading, "Thread", side_effect=thread_factory):
            manager = connect_manager.ConnectManager(
                logger=LoggerStub(),
                config=ConfigStub(),
                connect_creator=creator,
                ip_manager=IPManagerStub(),
                check_local_network=mock.Mock()
            )

            thread_factory.created = []
            host_info = {
                "ip_str": "1.1.1.1:443",
                "sni": "example.com",
                "host": "example.com"
            }
            ssl_sock = manager._create_ssl_connection(host_info)

        self.assertIsNotNone(ssl_sock)
        self.assertEqual(len(thread_factory.created), 0)
        self.assertEqual(len(creator.calls), 1)
        self.assertEqual(ssl_sock.host_info, host_info)

    def test_create_ssl_connection_reports_invalid_result(self):
        creator = mock.Mock()
        creator.connect_ssl.return_value = object()
        ip_manager = IPManagerStub()
        manager = connect_manager.ConnectManager(
            logger=LoggerStub(),
            config=ConfigStub(),
            connect_creator=creator,
            ip_manager=ip_manager,
            check_local_network=mock.Mock(is_ok=mock.Mock(return_value=True))
        )

        host_info = {
            "ip_str": "1.1.1.1:443",
            "sni": "example.com",
            "host": "example.com"
        }
        ssl_sock = manager._create_ssl_connection(host_info)

        self.assertIsNone(ssl_sock)
        self.assertEqual(len(ip_manager.fail_reports), 1)

    def test_create_more_connection_reuses_fixed_workers(self):
        creator = ConnectCreatorStub()
        thread_factory = FakeThreadFactory()

        with mock.patch.object(connect_manager.threading, "Thread", side_effect=thread_factory):
            manager = connect_manager.ConnectManager(
                logger=LoggerStub(),
                config=ConfigStub(),
                connect_creator=creator,
                ip_manager=IPManagerStub(),
                check_local_network=mock.Mock()
            )

            initial_threads = len(thread_factory.created)
            manager._connection_waiting_num = 1
            manager._create_more_connection()

        self.assertEqual(len(thread_factory.created), initial_threads)

    def test_stop_clears_pool_and_joins_background_threads(self):
        creator = ConnectCreatorStub()
        thread_factory = FakeThreadFactory()

        with mock.patch.object(connect_manager.threading, "Thread", side_effect=thread_factory):
            manager = connect_manager.ConnectManager(
                logger=LoggerStub(),
                config=ConfigStub(),
                connect_creator=creator,
                ip_manager=IPManagerStub(),
                check_local_network=mock.Mock()
            )

        sock = ClosableSock()
        manager.new_conn_pool.put((10, sock))
        manager.stop()

        self.assertTrue(sock.closed)
        self.assertEqual(manager.new_conn_pool.qsize(), 0)
        self.assertTrue(manager.keep_alive_th.join_called)
        for thread in manager.connect_threads:
            self.assertTrue(thread.join_called)

    def test_create_more_connection_skips_when_no_waiter(self):
        creator = ConnectCreatorStub()
        thread_factory = FakeThreadFactory()

        with mock.patch.object(connect_manager.threading, "Thread", side_effect=thread_factory):
            manager = connect_manager.ConnectManager(
                logger=LoggerStub(),
                config=ConfigStub(),
                connect_creator=creator,
                ip_manager=IPManagerStub(),
                check_local_network=mock.Mock()
            )

            initial_threads = len(thread_factory.created)
            manager._connection_waiting_num = 0
            manager._create_more_connection()

        self.assertEqual(len(thread_factory.created), initial_threads)

    def test_create_more_connection_skips_after_stop(self):
        creator = ConnectCreatorStub()
        thread_factory = FakeThreadFactory()

        with mock.patch.object(connect_manager.threading, "Thread", side_effect=thread_factory):
            manager = connect_manager.ConnectManager(
                logger=LoggerStub(),
                config=ConfigStub(),
                connect_creator=creator,
                ip_manager=IPManagerStub(),
                check_local_network=mock.Mock()
            )

            initial_threads = len(thread_factory.created)
            manager.running = False
            manager._connection_waiting_num = 1
            manager._create_more_connection()

        self.assertEqual(len(thread_factory.created), initial_threads)

    def test_connect_pool_get_need_keep_alive_skips_broken_sock(self):
        pool = connect_manager.ConnectPool()
        broken_sock = BrokenSock()
        good_sock = ClosableSock()
        good_sock.last_use_time = 0
        pool.put((1, broken_sock))
        pool.put((2, good_sock))

        result = pool.get_need_keep_alive(maxtime=1)

        self.assertEqual(result, [good_sock])
        self.assertNotIn(broken_sock, pool.pool)
        self.assertTrue(broken_sock.closed)

    def test_connect_pool_can_clear_broken_sock(self):
        pool = connect_manager.ConnectPool()
        broken_sock = BrokenSock()
        pool.put((1, broken_sock))

        pool.clear()

        self.assertTrue(broken_sock.closed)
        self.assertEqual(pool.qsize(), 0)

    def test_connect_pool_to_string_skips_broken_sock(self):
        pool = connect_manager.ConnectPool()
        broken_sock = BrokenSock()
        good_sock = ClosableSock()
        good_sock.last_use_time = 0
        pool.put((1, broken_sock))
        pool.put((2, good_sock))

        result = pool.to_string()

        self.assertIsInstance(result, str)
        self.assertIn(good_sock.ip_str, result)
