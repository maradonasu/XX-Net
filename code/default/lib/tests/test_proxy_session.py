#!/usr/bin/env python3
# coding:utf-8

import sys
import os
import time
import unittest.mock as mock

noarch_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.insert(0, noarch_lib)

code_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)

from unittest import TestCase

class TestProxySessionHelpers(TestCase):
    def test_traffic_readable(self):
        import x_tunnel.local.proxy_session as ps
        
        self.assertEqual(ps.traffic_readable(0), '0.0 B')
        self.assertEqual(ps.traffic_readable(512), '512.0 B')
        self.assertEqual(ps.traffic_readable(1024), '1.0 KB')
        self.assertEqual(ps.traffic_readable(1024 * 1024), '1.0 MB')
        self.assertEqual(ps.traffic_readable(1024 * 1024 * 1024), '1.0 GB')

    def test_traffic_readable_custom_units(self):
        import x_tunnel.local.proxy_session as ps
        
        custom_units = ('bytes', 'KB', 'MB', 'GB')
        self.assertEqual(ps.traffic_readable(1024, custom_units), '1.0 KB')

    def test_sleep_with_running_true(self):
        import x_tunnel.local.proxy_session as ps
        import x_tunnel.local.global_var as g
        
        g.running = True
        
        start_time = time.time()
        ps.sleep(0.1)
        elapsed = time.time() - start_time
        self.assertGreaterEqual(elapsed, 0.09)
        self.assertLess(elapsed, 0.2)
        
        g.running = False

    def test_sleep_with_running_false(self):
        import x_tunnel.local.proxy_session as ps
        import x_tunnel.local.global_var as g
        
        g.running = False
        
        start_time = time.time()
        ps.sleep(5)
        elapsed = time.time() - start_time
        self.assertLess(elapsed, 1)