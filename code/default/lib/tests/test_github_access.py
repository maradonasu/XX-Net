#!/usr/bin/env python3
# coding:utf-8

import unittest
import os
import sys
import time
import socket
import subprocess

current_path = os.path.dirname(os.path.abspath(__file__))
default_path = os.path.abspath(os.path.join(current_path, os.pardir, os.pardir, 'default'))
noarch_lib = os.path.abspath(os.path.join(default_path, 'lib', 'noarch'))
root_path = os.path.abspath(os.path.join(default_path, os.pardir, os.pardir))

sys.path.insert(0, noarch_lib)
sys.path.insert(0, default_path)

try:
    import simple_http_client
except ImportError:
    simple_http_client = None

try:
    import httpx
except ImportError:
    httpx = None


def check_port_open(host, port, timeout=2):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def wait_for_port(host, port, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_port_open(host, port):
            return True
        time.sleep(1)
    return False


class TestGitHubAccess(unittest.TestCase):
    """Test accessing GitHub through X-Tunnel proxy"""

    @classmethod
    def setUpClass(cls):
        cls.proxy_host = "127.0.0.1"
        cls.proxy_port = 1080
        cls.target_url = "https://github.com"
        cls.timeout = 30
        
        if not check_port_open(cls.proxy_host, cls.proxy_port):
            start_script = os.path.join(root_path, "start.bat")
            if os.path.exists(start_script):
                cls._process = subprocess.Popen(
                    [start_script],
                    cwd=root_path,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                wait_for_port(cls.proxy_host, cls.proxy_port, timeout=60)
                time.sleep(5)
            else:
                cls._process = None
        else:
            cls._process = None

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, '_process') and cls._process:
            cls._process.terminate()
            cls._process.wait()

    def setUp(self):
        if not check_port_open(self.proxy_host, self.proxy_port):
            self.skipTest(f"Proxy port {self.proxy_host}:{self.proxy_port} is not available")

    def test_access_github_via_http_proxy(self):
        """Test accessing GitHub through HTTP proxy (X-Tunnel)"""
        if simple_http_client is None:
            self.skipTest("simple_http_client not available")

        proxy = f"http://{self.proxy_host}:{self.proxy_port}"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res = simple_http_client.request(
                    "GET", 
                    self.target_url, 
                    proxy=proxy, 
                    timeout=self.timeout
                )
                if res and res.status == 200:
                    self.assertEqual(res.status, 200)
                    self.assertIsNotNone(res.text)
                    return
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                self.fail(f"Failed to access GitHub via HTTP proxy after {max_retries} attempts: {e}")

        self.fail(f"Failed to access GitHub via HTTP proxy, got status: {res.status if res else 'None'}")

    def test_access_github_via_socks5_proxy(self):
        """Test accessing GitHub through SOCKS5 proxy (X-Tunnel)"""
        if simple_http_client is None:
            self.skipTest("simple_http_client not available")

        proxy = f"socks5://{self.proxy_host}:{self.proxy_port}"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res = simple_http_client.request(
                    "GET", 
                    self.target_url, 
                    proxy=proxy, 
                    timeout=self.timeout
                )
                if res and res.status == 200:
                    self.assertEqual(res.status, 200)
                    self.assertIsNotNone(res.text)
                    return
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                self.fail(f"Failed to access GitHub via SOCKS5 proxy after {max_retries} attempts: {e}")

        self.fail(f"Failed to access GitHub via SOCKS5 proxy, got status: {res.status if res else 'None'}")

    def test_access_github_direct_httpx(self):
        """Test accessing GitHub using httpx library"""
        if httpx is None:
            self.skipTest("httpx not available")

        proxy_url = f"http://{self.proxy_host}:{self.proxy_port}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with httpx.Client(proxy=proxy_url, timeout=self.timeout) as client:
                    response = client.get(self.target_url)
                    if response.status_code == 200:
                        self.assertEqual(response.status_code, 200)
                        self.assertIn("github", response.text.lower())
                        return
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                self.fail(f"Failed to access GitHub via httpx after {max_retries} attempts: {e}")

    def test_access_github_api(self):
        """Test accessing GitHub API endpoint"""
        if simple_http_client is None:
            self.skipTest("simple_http_client not available")

        proxy = f"http://{self.proxy_host}:{self.proxy_port}"
        api_url = "https://api.github.com"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res = simple_http_client.request(
                    "GET", 
                    api_url, 
                    proxy=proxy, 
                    timeout=self.timeout
                )
                if res and res.status == 200:
                    self.assertEqual(res.status, 200)
                    return
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                self.fail(f"Failed to access GitHub API after {max_retries} attempts: {e}")

    def test_access_github_user_repo(self):
        """Test accessing a GitHub user repository page"""
        if simple_http_client is None:
            self.skipTest("simple_http_client not available")

        proxy = f"http://{self.proxy_host}:{self.proxy_port}"
        repo_url = "https://github.com/XX-net/XX-Net"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res = simple_http_client.request(
                    "GET", 
                    repo_url, 
                    proxy=proxy, 
                    timeout=self.timeout
                )
                if res and res.status == 200:
                    self.assertEqual(res.status, 200)
                    text = res.text if isinstance(res.text, str) else res.text.decode('utf-8', errors='ignore')
                    self.assertIn("XX-Net", text)
                    return
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                self.fail(f"Failed to access GitHub repo after {max_retries} attempts: {e}")


if __name__ == '__main__':
    unittest.main()