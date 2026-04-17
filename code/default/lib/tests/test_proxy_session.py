#!/usr/bin/env python3
# coding:utf-8

import sys
import os

noarch_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.insert(0, noarch_lib)

code_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)

from unittest import TestCase


class TestAsyncProxySessionHelpers(TestCase):
    def test_traffic_readable(self):
        from x_tunnel.local.async_proxy_session import traffic_readable
        
        self.assertEqual(traffic_readable(0), '0.0 B')
        self.assertEqual(traffic_readable(512), '512.0 B')
        self.assertEqual(traffic_readable(1024), '1.0 KB')
        self.assertEqual(traffic_readable(1024 * 1024), '1.0 MB')
        self.assertEqual(traffic_readable(1024 * 1024 * 1024), '1.0 GB')

    def test_traffic_readable_custom_units(self):
        from x_tunnel.local.async_proxy_session import traffic_readable
        
        custom_units = ('bytes', 'KB', 'MB', 'GB')
        self.assertEqual(traffic_readable(1024, custom_units), '1.0 KB')


class TestApiClientHelpers(TestCase):
    def test_get_app_name(self):
        from x_tunnel.local.api_client import get_app_name
        
        app_name = get_app_name()
        self.assertIsInstance(app_name, str)
        self.assertEqual(app_name, "XX-Net")

    def test_encrypt_decrypt_data(self):
        from x_tunnel.local.api_client import encrypt_data, decrypt_data
        from x_tunnel.local.context import ctx
        
        ctx.config = None
        original = b"test data"
        encrypted = encrypt_data(original)
        decrypted = decrypt_data(encrypted)
        self.assertEqual(decrypted, original)