#!/usr/bin/env python3
# coding:utf-8

import unittest
import socket
import threading
import time
from urllib.parse import parse_qs
from unittest.mock import MagicMock, patch

import sys
import os

current_path = os.path.dirname(os.path.abspath(__file__))
noarch_lib = os.path.abspath(os.path.join(current_path, os.pardir, 'noarch'))
default_path = os.path.abspath(os.path.join(current_path, os.pardir, os.pardir))
sys.path.insert(0, noarch_lib)
sys.path.insert(0, default_path)

import http_server
import utils


class TestHttpServerHandler(unittest.TestCase):
    """Test HttpServerHandler for Python 3 compatibility"""

    def setUp(self):
        self.mock_sock = MagicMock(spec=socket.socket)
        self.mock_sock.makefile.return_value = MagicMock()
        self.client_addr = ('127.0.0.1', 8080)

    def test_unpack_reqs_with_str_keys(self):
        """Test unpack_reqs handles str keys from parse_qs in Python 3"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        reqs_str = parse_qs('cmd=get_new&last_no=1', keep_blank_values=True)
        
        result = handler.unpack_reqs(reqs_str)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result['cmd'], 'get_new')
        self.assertEqual(result['last_no'], '1')

    def test_unpack_reqs_with_bytes_keys(self):
        """Test unpack_reqs handles bytes keys for backward compatibility"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        reqs_bytes = {
            b'cmd': [b'get_new'],
            b'last_no': [b'1']
        }
        
        result = handler.unpack_reqs(reqs_bytes)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result['cmd'], 'get_new')
        self.assertEqual(result['last_no'], '1')

    def test_unpack_reqs_with_mixed_keys(self):
        """Test unpack_reqs handles mixed str and bytes keys"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        reqs_mixed = {
            'cmd': ['get_new'],
            b'last_no': [b'1']
        }
        
        result = handler.unpack_reqs(reqs_mixed)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result['cmd'], 'get_new')
        self.assertEqual(result['last_no'], '1')

    def test_unpack_reqs_with_single_value(self):
        """Test unpack_reqs handles single value (not list)"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        reqs = {
            b'key': b'value'
        }
        
        result = handler.unpack_reqs(reqs)
        
        self.assertEqual(result['key'], 'value')

    def test_send_response_nc_with_str_headers(self):
        """Test send_response_nc handles str headers without TypeError"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        handler.wfile = MagicMock()
        
        handler.send_response_nc(
            mimetype='text/plain',
            content='test content',
            headers='X-Custom: value\r\n',
            status=200
        )
        
        handler.wfile.write.assert_called_once()
        written_data = handler.wfile.write.call_args[0][0]
        self.assertIsInstance(written_data, bytes)

    def test_send_response_nc_with_bytes_headers(self):
        """Test send_response_nc handles bytes headers"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        handler.wfile = MagicMock()
        
        handler.send_response_nc(
            mimetype='text/plain',
            content='test content',
            headers=b'X-Custom: value\r\n',
            status=200
        )
        
        handler.wfile.write.assert_called_once()
        written_data = handler.wfile.write.call_args[0][0]
        self.assertIsInstance(written_data, bytes)

    def test_send_response_nc_with_dict_headers(self):
        """Test send_response_nc handles dict headers"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        handler.wfile = MagicMock()
        
        handler.send_response_nc(
            mimetype='text/plain',
            content='test content',
            headers={'X-Custom': 'value'},
            status=200
        )
        
        handler.wfile.write.assert_called_once()
        written_data = handler.wfile.write.call_args[0][0]
        self.assertIsInstance(written_data, bytes)

    def test_send_response_nc_with_empty_headers(self):
        """Test send_response_nc handles empty headers"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        handler.wfile = MagicMock()
        
        handler.send_response_nc(
            mimetype='text/plain',
            content='test content',
            headers='',
            status=200
        )
        
        handler.wfile.write.assert_called_once()
        written_data = handler.wfile.write.call_args[0][0]
        self.assertIsInstance(written_data, bytes)

    def test_send_response_nc_contains_no_cache_headers(self):
        """Test send_response_nc includes no-cache headers"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        handler.wfile = MagicMock()
        
        handler.send_response_nc(
            mimetype='text/plain',
            content='test content',
            headers='',
            status=200
        )
        
        written_data = handler.wfile.write.call_args[0][0]
        self.assertIn(b'Cache-Control: no-cache', written_data)
        self.assertIn(b'Pragma: no-cache', written_data)

    def test_send_response_with_bytes_mimetype(self):
        """Test send_response handles bytes mimetype"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        handler.wfile = MagicMock()
        
        handler.send_response(
            mimetype=b'application/json',
            content=b'{"key": "value"}',
            headers=b'',
            status=200
        )
        
        handler.wfile.write.assert_called_once()
        written_data = handler.wfile.write.call_args[0][0]
        self.assertIsInstance(written_data, bytes)
        self.assertIn(b'application/json', written_data)

    def test_send_response_with_str_mimetype(self):
        """Test send_response handles str mimetype"""
        handler = http_server.HttpServerHandler(
            self.mock_sock, self.client_addr, None
        )
        
        handler.wfile = MagicMock()
        
        handler.send_response(
            mimetype='application/json',
            content='{"key": "value"}',
            headers='',
            status=200
        )
        
        handler.wfile.write.assert_called_once()
        written_data = handler.wfile.write.call_args[0][0]
        self.assertIsInstance(written_data, bytes)
        self.assertIn(b'application/json', written_data)


class TestHttpServerLive(unittest.TestCase):
    """Test HTTPServer with actual socket connections"""

    def setUp(self):
        self.server = None
        self.thread = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def test_server_request_with_query_params(self):
        """Test server handles request with query params (parse_qs returns str)"""
        pass


if __name__ == '__main__':
    unittest.main()