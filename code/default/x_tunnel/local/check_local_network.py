import os
import threading
import time

import http_client
import utils
from log_buffer import getLogger

xlog = getLogger("x_tunnel")


class CheckNetwork(object):
    check_valid = 30
    timeout = 5

    def __init__(self, network_type="IPv4"):
        self.type = network_type
        self.urls = []
        self._checking_lock = threading.Lock()
        self._checking_num = 0
        self.network_stat = "unknown"
        self.last_check_time = 0
        self.continue_fail_count = 0
        self.http_client = http_client.Client(timeout=self.timeout)
        self.rules = self._load_rules()

    def _load_rules(self):
        try:
            from .context import ctx
            config = getattr(ctx, "config", None)
            if config:
                return getattr(config, "check_local_network_rules", "normal")
        except Exception:
            pass

        return "normal"

    def report_ok(self):
        self.network_stat = "OK"
        self.last_check_time = time.time()
        self.continue_fail_count = 0

    def report_fail(self):
        self.continue_fail_count += 1
        if self.continue_fail_count > 1:
            xlog.debug("report_connect_fail %s continue_fail_count:%d", self.type, self.continue_fail_count)
            if time.time() - self.last_check_time > self.check_valid:
                self.triger_check_network(True)

    def get_stat(self):
        rules = self._load_rules()
        if rules == "force_fail":
            return "Fail"
        if rules == "force_ok":
            return "OK"
        return self.network_stat

    def is_ok(self):
        if self.network_stat == "unknown" or time.time() - self.last_check_time > self.check_valid:
            self.triger_check_network(True)

        rules = self._load_rules()
        if rules == "normal":
            return self.network_stat == "OK" and time.time() - self.last_check_time < self.check_valid + self.timeout
        if rules == "force_fail":
            return False
        if rules == "force_ok":
            return True
        return self.network_stat == "OK"

    def _test_host(self, url):
        try:
            headers = {
                "user-agent": "Mozilla/5.0",
                "accept": "application/json, text/javascript, */*; q=0.01",
                "connection": "keep-alive",
            }
            response = self.http_client.request("HEAD", url, headers, "", read_payload=False)
            return bool(response)
        except Exception:
            return False

    def _simple_check_worker(self):
        started = time.time()
        try:
            network_ok = False
            for url in self.urls:
                if self._test_host(url):
                    network_ok = True
                    break
                time.sleep(1)

            if network_ok:
                self.last_check_time = time.time()
                self.report_ok()
                xlog.debug("network %s is ok, cost:%d ms", self.type, 1000 * (time.time() - started))
            else:
                xlog.warn("network %s fail", self.type)
                self.network_stat = "Fail"
                self.last_check_time = time.time()
        finally:
            with self._checking_lock:
                self._checking_num -= 1

    def triger_check_network(self, fail=False, force=False):
        now = time.time()
        with self._checking_lock:
            if not force:
                if self._checking_num > 0:
                    return

                if fail or self.network_stat != "OK":
                    if now - self.last_check_time < 3:
                        return
                elif now - self.last_check_time < 10:
                    return

            self.last_check_time = now
            self._checking_num += 1

        thread = threading.Thread(target=self._simple_check_worker, name="network_checker")
        thread.daemon = True
        try:
            thread.start()
        except Exception:
            with self._checking_lock:
                self._checking_num -= 1
            raise


IPv4 = CheckNetwork("IPv4")
IPv4.urls = [
    "https://www.bing.com",
    "https://cdn.bootcdn.net",
    "https://cdn.staticfile.org",
]

IPv6 = CheckNetwork("IPv6")
IPv6.urls = [
    "https://ipv6.vm3.test-ipv6.com",
    "https://ipv6.lookup.test-ipv6.com",
    "https://v6.myip.la",
]


def report_ok(ip):
    if "." in utils.to_str(ip):
        IPv4.report_ok()
    else:
        IPv6.report_ok()


def report_fail(ip):
    if "." in utils.to_str(ip):
        IPv4.report_fail()
    else:
        IPv6.report_fail()


def is_ok(ip=None):
    ip = utils.to_str(ip)
    if not ip:
        return IPv4.is_ok() or IPv6.is_ok()
    if "." in ip:
        return IPv4.is_ok()
    return IPv6.is_ok()
