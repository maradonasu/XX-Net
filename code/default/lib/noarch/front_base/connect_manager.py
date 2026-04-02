#!/usr/bin/env python3
# coding:utf-8


"""
This file manage the ssl connection pool.
For faster access the target host,

ssl link will save to pool after use.
and need keep alive every 60 seconds.

We create multi-thread to try-connect google cloud ip.

we also keep host connect for direct connect.
every ssl connect can't change host after request.
"""

import time
import threading
import operator
import socket
import random

from .openssl_wrap import SSLConnection

class NoRescourceException(Exception):
    pass


class ConnectPool():
    def __init__(self):
        self.pool_lock = threading.Lock()
        self.not_empty = threading.Condition(self.pool_lock)
        self.pool = {}

    def qsize(self):
        return len(self.pool)

    def put(self, item):
        handshake_time, sock = item
        self.not_empty.acquire()
        try:
            self.pool[sock] = handshake_time
            self.not_empty.notify()
        finally:
            self.not_empty.release()

    def get(self, block=True, timeout=None):
        self.not_empty.acquire()
        try:
            if not block:
                if self.qsize() == 0:
                    return None
            elif timeout is None:
                while self.qsize() == 0:
                    self.not_empty.wait()
            elif timeout < 0:
                raise ValueError("'timeout' must be a positive number")
            else:
                end_time = time.time() + timeout
                while not self.qsize():
                    remaining = end_time - time.time()
                    if remaining <= 0.0:
                        return None
                    self.not_empty.wait(remaining)

            item = self._get()
            return item
        finally:
            self.not_empty.release()

    def get_nowait(self):
        return self.get(block=False)

    def _get(self):
        fastest_time = 9999
        fastest_sock = None
        for sock in self.pool:
            hs_time = self.pool[sock]
            if hs_time < fastest_time or not fastest_sock:
                fastest_time = hs_time
                fastest_sock = sock

        self.pool.pop(fastest_sock)
        return fastest_time, fastest_sock

    def get_slowest(self):
        self.not_empty.acquire()
        try:
            if not self.qsize():
                raise ValueError("no item")

            slowest_handshake_time = 0
            slowest_sock = None
            for sock in self.pool:
                handshake_time = self.pool[sock]
                if handshake_time > slowest_handshake_time:
                    slowest_handshake_time = handshake_time
                    slowest_sock = sock

            self.pool.pop(slowest_sock)
            return slowest_handshake_time, slowest_sock
        finally:
            self.not_empty.release()

    def get_need_keep_alive(self, maxtime=200):
        return_list = []
        self.pool_lock.acquire()
        try:
            pool = tuple(self.pool)
            for sock in pool:
                last_use_time = getattr(sock, "last_use_time", None)
                if last_use_time is None:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    self.pool.pop(sock, None)
                    continue

                inactive_time = time.time() - last_use_time
                # self.logger.debug("inactive_time:%d", inactive_time * 1000)
                if inactive_time >= maxtime:
                    return_list.append(sock)

                    del self.pool[sock]

            return return_list
        finally:
            self.pool_lock.release()

    def clear(self):
        self.pool_lock.acquire()
        try:
            for sock in self.pool:
                sock.close()

            self.pool = {}
        finally:
            self.pool_lock.release()

    def to_string(self):
        out_str = ''
        self.pool_lock.acquire()
        try:
            pool = sorted(list(self.pool.items()), key=operator.itemgetter(1))
            i = 0
            for item in pool:
                sock, t = item
                ip_str = getattr(sock, "ip_str", "unknown")
                last_use_time = getattr(sock, "last_use_time", None)
                if last_use_time is None:
                    not_active_time = -1
                else:
                    not_active_time = time.time() - last_use_time
                out_str += "%d \t %s handshake:%d not_active_time:%d \r\n" % (i, ip_str, t, not_active_time)
                i += 1
        finally:
            self.pool_lock.release()

        return out_str


class ConnectManager(object):
    def __init__(self, logger, config, connect_creator, ip_manager, check_local_network):
        self.class_name = "ConnectManager"
        self.logger = logger
        self.config = config
        self._normalize_config()
        self.connect_creator = connect_creator
        self.ip_manager = ip_manager
        self.check_local_network = check_local_network

        self.connect_thread_cond = threading.Condition()
        self.timeout = 4
        self.start_connect_time = 0
        self.running = True

        self._waiting_num_lock = threading.Lock()
        self._connection_waiting_num = 0
        self.no_ip_lock = threading.Lock()
        self.no_ip_time = 0

        # after new created ssl_sock timeout(50 seconds)
        # call the callback.
        # This callback will put ssl to worker
        self.ssl_timeout_cb = None
        
        self.new_conn_pool = ConnectPool()

        self.connect_threads = []

        self.keep_alive_th = threading.Thread(target=self.keep_alive_thread,
                                              name="%s_conn_manager_keep_alive" % self.logger.name)
        self.keep_alive_th.daemon = True
        self.keep_alive_th.start()

        if self.config.connection_pool_min:
            self.keep_conn_th = threading.Thread(target=self.keep_connection_daemon,
                                                 name="%s_conn_manager_keep_conn" % self.logger.name)
            self.keep_conn_th.daemon = True
            self.keep_conn_th.start()
        else:
            self.keep_conn_th = None

        for _ in range(self.config.https_max_connect_thread):
            connect_thread = threading.Thread(target=self._connect_thread,
                                              name="%s_conn_manager__connect_th" % self.logger.name)
            connect_thread.daemon = True
            connect_thread.start()
            self.connect_threads.append(connect_thread)

    def _normalize_config(self):
        if getattr(self.config, "https_max_connect_thread", 0) < 1:
            self.config.https_max_connect_thread = 1

        if getattr(self.config, "https_keep_alive", 0) < 7:
            self.config.https_keep_alive = 7

        if getattr(self.config, "https_connection_pool_max", 0) < 0:
            self.config.https_connection_pool_max = 0

        if getattr(self.config, "https_connection_pool_min", 0) < 0:
            self.config.https_connection_pool_min = 0

        if self.config.https_connection_pool_min > self.config.https_connection_pool_max:
            self.config.https_connection_pool_min = self.config.https_connection_pool_max

    def stop(self):
        self.running = False
        self.new_conn_pool.clear()
        with self.connect_thread_cond:
            self.connect_thread_cond.notify_all()

        if self.keep_alive_th.is_alive() and self.keep_alive_th is not threading.current_thread():
            self.keep_alive_th.join(5)

        if self.keep_conn_th and self.keep_conn_th.is_alive() and self.keep_conn_th is not threading.current_thread():
            self.keep_conn_th.join(5)

        for thread in self.connect_threads:
            if thread.is_alive() and thread is not threading.current_thread():
                thread.join(5)

    def set_ssl_created_cb(self, cb):
        self.ssl_timeout_cb = cb

    def keep_alive_thread(self):
        while self.running:
            to_keep_live_list = self.new_conn_pool.get_need_keep_alive(maxtime=self.config.https_keep_alive-6)

            for ssl_sock in to_keep_live_list:
                inactive_time = time.time() - ssl_sock.last_use_time
                if inactive_time > self.config.https_keep_alive or not self.ssl_timeout_cb:
                    self.ip_manager.report_connect_closed(ssl_sock.ip_str, ssl_sock.sni, "alive_timeout")
                    ssl_sock.close()
                else:
                    # put ssl to worker
                    try:
                        self.ssl_timeout_cb(ssl_sock)
                    except Exception as e:
                        self.logger.exception("ssl_timeout_cb except:%r", e)
                        # no appid avaiable
                        pass

            time.sleep(5)

    def keep_connection_daemon(self):
        while self.running:
            if self.new_conn_pool.qsize() >= self.config.https_connection_pool_min:
                time.sleep(5)
                continue

            if self.config.show_state_debug:
                self.logger.debug("call _create_more_connection from keep_connection_daemon")
            self._create_more_connection()
            time.sleep(1)

    def _need_more_ip(self):
        return bool(self._connection_waiting_num)

    def _need_keep_connection(self):
        if not self.keep_conn_th:
            return False

        return self.new_conn_pool.qsize() < self.config.https_connection_pool_min

    def _need_more_connection(self):
        return self._need_more_ip() or self._need_keep_connection()

    def _create_more_connection(self):
        if self.config.show_state_debug:
            self.logger.debug("_create_more_connection")
        if not self.running or not self._need_more_connection():
            return

        with self.connect_thread_cond:
            self.connect_thread_cond.notify_all()

    def _connect_thread(self, sleep_time=0):
        if self.config.show_state_debug:
            self.logger.debug("_connect_thread")

        if sleep_time > 0.1:
            self.logger.debug("_connect_thread sleep %f", sleep_time)
            time.sleep(sleep_time)

        while self.running:
            with self.connect_thread_cond:
                while self.running:
                    if self._need_more_connection() and time.time() - self.no_ip_time > 10 and \
                            self.new_conn_pool.qsize() <= self.config.https_connection_pool_max:
                        break
                    self.connect_thread_cond.wait(1)

            if not self.running:
                break

            if self.config.show_state_debug:
                self.logger.debug("call _connect_process from _connect_thread")
            self.start_connect_time = time.time()
            self._connect_process()
            self.start_connect_time = 0

    def _connect_process(self):
        if self.config.show_state_debug:
            self.logger.debug("_connect_process")
        try:
            host_info = self.ip_manager.get_ip_sni_host()
            if not host_info:
                self.no_ip_time = time.time()
                with self.no_ip_lock:
                    self.logger.warning("not enough ip")
                    time.sleep(1)
                return None

            # self.logger.debug("create ssl conn %s", ip_str)
            ssl_sock = self._create_ssl_connection(host_info)
            if not ssl_sock:
                return None

            self.new_conn_pool.put((ssl_sock.handshake_time, ssl_sock))

            if self.config.connect_create_interval > 0.1:
                sleep = random.uniform(self.config.connect_create_interval, self.config.connect_create_interval*2)
                time.sleep(sleep)

            return ssl_sock
        except Exception as e:
            self.logger.exception("connect_process except:%r", e)

    def _create_ssl_connection(self, host_info):
        if self.config.show_state_debug:
            self.logger.debug("_create_ssl_connection")

        ip_str = host_info["ip_str"]
        sni = host_info["sni"]
        host = host_info["host"]

        try:
            ssl_sock = self.connect_creator.connect_ssl(ip_str, sni, host, close_cb=self.ip_manager.ssl_closed)
            if not ssl_sock or isinstance(ssl_sock, ValueError) or isinstance(ssl_sock, OSError) or \
                    not hasattr(ssl_sock, "handshake_time"):
                raise socket.error("timeout")

            self.ip_manager.update_ip(ip_str, sni, ssl_sock.handshake_time)
            self.logger.debug("create_ssl update ip:%s time:%d h2:%d sni:%s, host:%s",
                              ip_str, ssl_sock.handshake_time, ssl_sock.h2, ssl_sock.sni, ssl_sock.host)
            ssl_sock.host_info = host_info

            return ssl_sock
        except socket.error as e:
            if str(e) in ["no host", "timeout"]:
                pass
            elif not self.check_local_network.is_ok(ip_str):
                self.logger.debug("connect %s network fail, %r", ip_str, e)
                time.sleep(1)
            else:
                self.logger.debug("connect %s fail:%r", ip_str, e)
            self.ip_manager.report_connect_fail(ip_str, sni, str(e))
        except NoRescourceException as e:
            self.logger.warning("create ssl for %s except:%r", ip_str, e)
            self.ip_manager.report_connect_fail(ip_str, sni, str(e))
        except Exception as e:
            self.logger.exception("connect except:%r", e)
            self.ip_manager.report_connect_fail(ip_str, sni, str(e))
            if not self.check_local_network.is_ok(ip_str):
                self.logger.debug("connect %s network fail, %r", ip_str, e)
                time.sleep(10)
            else:
                self.logger.exception("connect %s fail:%r", ip_str, e)
                time.sleep(1)

    def get_ssl_connection(self, timeout=30):
        with self._waiting_num_lock:
            self._connection_waiting_num += 1

        end_time = time.monotonic() + max(timeout, 0)
        try:
            while self.running:
                ret = self.new_conn_pool.get(block=False)
                if timeout <= 0 and not ret:
                    return None

                if not ret:
                    self._create_more_connection()
                    remaining = end_time - time.monotonic()
                    if remaining <= 0:
                        self.logger.debug("get_ssl_connection timeout")
                        return None
                    ret = self.new_conn_pool.get(block=True, timeout=remaining)

                if ret:
                    handshake_time, ssl_sock = ret
                    if time.time() - ssl_sock.last_use_time < self.config.https_keep_alive - 1:
                        if self.config.show_state_debug:
                            self.logger.debug("new_conn_pool.get:%s handshake:%d", ssl_sock.ip, handshake_time)
                        return ssl_sock
                    else:
                        self.logger.warn("new_conn_pool.get:%s handshake:%d timeout.", ssl_sock.ip, handshake_time)
                        self.ip_manager.report_connect_closed(ssl_sock.ip_str, ssl_sock.sni, "get_ssl_timeout")
                        ssl_sock.close()
                else:
                    if time.monotonic() > end_time:
                        self.logger.debug("get_ssl_connection timeout")
                        return None

                self._create_more_connection()
        finally:
            with self._waiting_num_lock:
                self._connection_waiting_num -= 1
