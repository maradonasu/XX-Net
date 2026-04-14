import unittest
import os
import sys
import time
import socket
import struct
import threading

current_path = os.path.dirname(os.path.abspath(__file__))
default_path = os.path.abspath(os.path.join(current_path, os.pardir, os.pardir))
root_path = os.path.abspath(os.path.join(default_path, os.pardir, os.pardir))

noarch_lib = os.path.abspath(os.path.join(default_path, 'lib', 'noarch'))
sys.path.insert(0, noarch_lib)
sys.path.insert(0, default_path)

import utils


class XTunnelSocks5Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._xtunnel_started = False
        cls._start_timeout = 60
        
        xtunnel_lib = os.path.abspath(os.path.join(default_path, 'x_tunnel', 'local'))
        if xtunnel_lib not in sys.path:
            sys.path.insert(0, xtunnel_lib)
        
        try:
            from x_tunnel.local import client as xtunnel_client
            from x_tunnel.local import global_var as g
            
            cls._xtunnel_client = xtunnel_client
            cls._g = g
            
            if not xtunnel_client.ready:
                def start_xtunnel():
                    try:
                        xtunnel_client.start({})
                    except Exception as e:
                        print(f"XTunnel start error: {e}")
                
                cls._start_thread = threading.Thread(target=start_xtunnel, name="xtunnel_start")
                cls._start_thread.daemon = True
                cls._start_thread.start()
                
                start_time = time.time()
                while time.time() - start_time < cls._start_timeout:
                    if xtunnel_client.ready:
                        cls._xtunnel_started = True
                        break
                    time.sleep(1)
                
                if not cls._xtunnel_started:
                    raise Exception("XTunnel failed to start within timeout")
            else:
                cls._xtunnel_started = True
                
        except Exception as e:
            raise Exception(f"Failed to initialize XTunnel: {e}")

    @classmethod
    def tearDownClass(cls):
        if cls._xtunnel_started and hasattr(cls, '_xtunnel_client'):
            try:
                cls._xtunnel_client.stop()
                time.sleep(2)
            except Exception as e:
                print(f"XTunnel stop error: {e}")

    def _is_port_open(self, host, port, timeout=5):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            result = sock.connect_ex((host, port))
            return result == 0
        except Exception:
            return False
        finally:
            sock.close()

    def test_socks5_port_open(self):
        self.assertTrue(self._xtunnel_started, "XTunnel should be started")
        
        port = getattr(self._g, 'bind_port', 1080)
        self.assertTrue(self._is_port_open('127.0.0.1', port), 
                        f"SOCKS5 port {port} should be open")

    def test_socks5_proxy_github(self):
        self.assertTrue(self._xtunnel_started, "XTunnel should be started")
        
        import socks
        port = getattr(self._g, 'bind_port', 1080)
        
        sock = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
        sock.set_proxy(proxy_type=socks.SOCKS5, addr='127.0.0.1', port=port)
        sock.settimeout(30)
        
        try:
            sock.connect(('github.com', 443))
            
            import ssl
            context = ssl.create_default_context()
            ssl_sock = context.wrap_socket(sock, server_hostname='github.com')
            
            ssl_sock.send(b'GET / HTTP/1.1\r\nHost: github.com\r\nConnection: close\r\n\r\n')
            
            response = b''
            while True:
                data = ssl_sock.recv(4096)
                if not data:
                    break
                response += data
            
            self.assertTrue(len(response) > 0, "Response should not be empty")
            self.assertIn(b'HTTP/1.1', response[:20], "Response should start with HTTP/1.1")
            
            status_line = response.split(b'\r\n')[0]
            self.assertIn(b'200', status_line, "Status should be 200 OK")
            
            ssl_sock.close()
            
        except Exception as e:
            self.fail(f"SOCKS5 proxy connection to github.com failed: {e}")

    def test_socks5_proxy_raw_http(self):
        self.assertTrue(self._xtunnel_started, "XTunnel should be started")
        
        port = getattr(self._g, 'bind_port', 1080)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        try:
            sock.connect(('127.0.0.1', port))
            
            sock.send(b'\x05\x01\x00')
            response = sock.recv(2)
            self.assertEqual(response, b'\x05\x00', "SOCKS5 handshake should succeed")
            
            host = 'github.com'
            host_bytes = host.encode('ascii')
            port_bytes = struct.pack('>H', 443)
            request = b'\x05\x01\x00\x03' + bytes([len(host_bytes)]) + host_bytes + port_bytes
            sock.send(request)
            
            response = sock.recv(10)
            self.assertEqual(response[0:2], b'\x05\x00', "SOCKS5 connect should succeed")
            
            sock.close()
            
        except Exception as e:
            self.fail(f"Raw SOCKS5 protocol test failed: {e}")


if __name__ == '__main__':
    unittest.main()