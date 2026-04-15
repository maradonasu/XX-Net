#!/usr/bin/env python3
# coding:utf-8

import sys
import os
import threading

noarch_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.insert(0, noarch_lib)

code_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)

from unittest import TestCase

class TestConnectCreatorInit(TestCase):
    def test_init_defaults(self):
        import unittest.mock as mock
        from front_base import connect_creator
        
        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        mock_config.socket_timeout = 5
        mock_config.show_state_debug = False
        mock_config.PROXY_ENABLE = 0
        mock_config.connect_force_http1 = False
        mock_config.connect_force_http2 = False
        
        creator = connect_creator.ConnectCreator(mock_logger, mock_config)
        
        self.assertEqual(creator.timeout, 5)
        self.assertFalse(creator.debug)
        self.assertIsNotNone(creator.check_cert)

    def test_init_with_custom_timeout(self):
        import unittest.mock as mock
        from front_base import connect_creator
        
        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        mock_config.socket_timeout = 10
        mock_config.show_state_debug = False
        mock_config.PROXY_ENABLE = 0
        mock_config.connect_force_http1 = False
        mock_config.connect_force_http2 = False
        
        creator = connect_creator.ConnectCreator(mock_logger, mock_config)
        
        self.assertEqual(creator.timeout, 10)

    def test_init_with_debug(self):
        import unittest.mock as mock
        from front_base import connect_creator
        
        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        mock_config.socket_timeout = 5
        mock_config.show_state_debug = True
        mock_config.PROXY_ENABLE = 0
        mock_config.connect_force_http1 = False
        mock_config.connect_force_http2 = False
        
        creator = connect_creator.ConnectCreator(mock_logger, mock_config, debug=True)
        
        self.assertTrue(creator.debug)

    def test_init_with_custom_check_cert(self):
        import unittest.mock as mock
        from front_base import connect_creator
        
        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        mock_config.socket_timeout = 5
        mock_config.show_state_debug = False
        mock_config.PROXY_ENABLE = 0
        mock_config.connect_force_http1 = False
        mock_config.connect_force_http2 = False
        
        custom_check = lambda x: None
        creator = connect_creator.ConnectCreator(mock_logger, mock_config, check_cert=custom_check)
        
        self.assertEqual(creator.check_cert, custom_check)

class TestConnectCreatorProxySetup(TestCase):
    def test_update_config_no_proxy(self):
        import unittest.mock as mock
        from front_base import connect_creator
        
        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        mock_config.socket_timeout = 5
        mock_config.show_state_debug = False
        mock_config.PROXY_ENABLE = 0
        mock_config.connect_force_http1 = False
        mock_config.connect_force_http2 = False
        
        creator = connect_creator.ConnectCreator(mock_logger, mock_config)
        creator.update_config()

    def test_update_config_http_proxy(self):
        import unittest.mock as mock
        from front_base import connect_creator
        import socks
        
        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        mock_config.socket_timeout = 5
        mock_config.show_state_debug = False
        mock_config.PROXY_ENABLE = 1
        mock_config.PROXY_TYPE = "HTTP"
        mock_config.PROXY_HOST = "127.0.0.1"
        mock_config.PROXY_PORT = 8080
        mock_config.PROXY_USER = None
        mock_config.PROXY_PASSWD = None
        mock_config.connect_force_http1 = False
        mock_config.connect_force_http2 = False
        
        creator = connect_creator.ConnectCreator(mock_logger, mock_config)
        creator.update_config()

    def test_update_config_socks5_proxy(self):
        import unittest.mock as mock
        from front_base import connect_creator
        
        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        mock_config.socket_timeout = 5
        mock_config.show_state_debug = False
        mock_config.PROXY_ENABLE = 1
        mock_config.PROXY_TYPE = "SOCKS5"
        mock_config.PROXY_HOST = "127.0.0.1"
        mock_config.PROXY_PORT = 1080
        mock_config.PROXY_USER = None
        mock_config.PROXY_PASSWD = None
        mock_config.connect_force_http1 = False
        mock_config.connect_force_http2 = False
        
        creator = connect_creator.ConnectCreator(mock_logger, mock_config)
        creator.update_config()

    def test_update_config_invalid_proxy_type(self):
        import unittest.mock as mock
        from front_base import connect_creator
        
        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        mock_config.socket_timeout = 5
        mock_config.show_state_debug = False
        mock_config.PROXY_ENABLE = 1
        mock_config.PROXY_TYPE = "INVALID"
        mock_config.connect_force_http1 = False
        mock_config.connect_force_http2 = False
        
        with self.assertRaises(Exception):
            connect_creator.ConnectCreator(mock_logger, mock_config)