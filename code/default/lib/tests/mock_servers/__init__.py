#!/usr/bin/env python3
# coding:utf-8

import threading
import socket
import time
from typing import Callable, Optional

class MockServerBase:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._handler: Callable = lambda: None

    def start(self) -> int:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.port = self.server_socket.getsockname()[1]
        self.running = True
        self.thread = threading.Thread(target=self._serve_loop, daemon=True)
        self.thread.start()
        time.sleep(0.1)
        return self.port

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if self.thread:
            self.thread.join(timeout=1)

    def _serve_loop(self):
        while self.running:
            try:
                self.server_socket.settimeout(0.5)
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_connection, args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    continue
                break

    def _handle_connection(self, conn: socket.socket, addr: tuple):
        try:
            self._handler(conn, addr)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def set_handler(self, handler: Callable):
        self._handler = handler