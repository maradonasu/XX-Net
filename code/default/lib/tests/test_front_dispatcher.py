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
import unittest.mock as mock

class TestFrontDispatcherState(TestCase):
    def test_module_globals_exist(self):
        import x_tunnel.local.front_dispatcher as fd
        
        self.assertIsInstance(fd.all_fronts, list)
        self.assertIsInstance(fd.light_fronts, list)
        self.assertIsInstance(fd.session_fronts, list)
        self.assertIsNone(fd.cloudflare_front)
        self.assertFalse(fd._initialized)

    def test_fail_count_tracking(self):
        import x_tunnel.local.front_dispatcher as fd
        
        fd._front_fail_counts.clear()
        fd._front_last_fail_time.clear()
        
        fd._front_fail_counts["test_front"] = 5
        fd._front_last_fail_time["test_front"] = 100.0
        
        self.assertEqual(fd._front_fail_counts["test_front"], 5)
        self.assertEqual(fd._front_last_fail_time["test_front"], 100.0)

    def test_constants_defined(self):
        import x_tunnel.local.front_dispatcher as fd
        
        self.assertEqual(fd.FRONT_FAIL_BASE_PENALTY, 1000)
        self.assertEqual(fd.FRONT_PENALTY_DECAY_SECONDS, 30)

class TestFrontDispatcherFunctions(TestCase):
    def test_stop_without_init(self):
        import x_tunnel.local.front_dispatcher as fd
        
        fd._initialized = False
        fd._statistic_running = False
        fd.stop()

    def test_init_function_exists(self):
        import x_tunnel.local.front_dispatcher as fd
        
        self.assertTrue(hasattr(fd, 'init'))

    def test_stop_function_exists(self):
        import x_tunnel.local.front_dispatcher as fd
        
        self.assertTrue(hasattr(fd, 'stop'))

    def test_get_front_function_exists(self):
        import x_tunnel.local.front_dispatcher as fd
        
        self.assertTrue(hasattr(fd, 'get_front'))

    def test_save_cloudflare_domain_function_exists(self):
        import x_tunnel.local.front_dispatcher as fd
        
        self.assertTrue(hasattr(fd, 'save_cloudflare_domain'))

    def test_front_staticstic_thread_function_exists(self):
        import x_tunnel.local.front_dispatcher as fd
        
        self.assertTrue(hasattr(fd, 'front_staticstic_thread'))