#!/usr/bin/env python3
# coding:utf-8

import sys
import os
import time
import socket
import threading

noarch_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.insert(0, noarch_lib)

from unittest import TestCase
from mock_servers.http_mock import HTTPMockServer
from mock_servers.socks5_mock import SOCKS5MockTarget, MockSOCKS5Client

class IntegrationTestFramework(TestCase):
    def setUp(self):
        self.http_mock = HTTPMockServer()
        self.target_mock = SOCKS5MockTarget()

    def tearDown(self):
        self.http_mock.stop()
        self.target_mock.stop()

    def test_http_mock_server_starts(self):
        port = self.http_mock.start()
        self.assertGreater(port, 0)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", port))
            sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response = sock.recv(4096)
            self.assertIn(b"HTTP/1.1 200", response)
            self.assertIn(b"OK", response)
        finally:
            sock.close()

    def test_http_mock_custom_response(self):
        self.http_mock.set_response(status=404, body=b"Not Found", headers={"Content-Type": "text/html"})
        port = self.http_mock.start()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", port))
            sock.sendall(b"GET /missing HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response = sock.recv(4096)
            self.assertIn(b"HTTP/1.1 404", response)
            self.assertIn(b"Not Found", response)
        finally:
            sock.close()

    def test_socks5_mock_target(self):
        port = self.target_mock.start()
        self.assertGreater(port, 0)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", port))
            sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response = sock.recv(4096)
            self.assertIn(b"HTTP/1.1 200", response)
        finally:
            sock.close()

    def test_http_mock_custom_handler(self):
        custom_responses = []

        def custom_handler(conn, addr):
            request = conn.recv(4096)
            custom_responses.append(request)
            conn.sendall(b"HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\n\r\n")

        self.http_mock.set_custom_handler(custom_handler)
        port = self.http_mock.start()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", port))
            sock.sendall(b"POST /api HTTP/1.1\r\nHost: localhost\r\nContent-Length: 5\r\n\r\nhello")
            response = sock.recv(4096)
            self.assertIn(b"HTTP/1.1 202", response)
            self.assertEqual(len(custom_responses), 1)
            self.assertIn(b"POST /api", custom_responses[0])
        finally:
            sock.close()

    def test_concurrent_connections(self):
        port = self.http_mock.start()
        results = []

        def make_request():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            try:
                sock.connect(("127.0.0.1", port))
                sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                response = sock.recv(4096)
                results.append(b"200" in response)
            except Exception as e:
                results.append(False)
            finally:
                sock.close()

        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(len(results), 5)
        self.assertTrue(all(results))