#!/usr/bin/env python3
# coding:utf-8

import socket
from typing import Optional
from mock_servers import MockServerBase

class SOCKS5MockTarget(MockServerBase):
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        super().__init__(host, port)
        self.response_data = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
        self._custom_handler: Optional[callable] = None

    def set_response(self, data: bytes):
        self.response_data = data

    def set_custom_handler(self, handler: callable):
        self._custom_handler = handler

    def _handle_connection(self, conn: socket.socket, addr: tuple):
        try:
            if self._custom_handler:
                self._custom_handler(conn, addr)
                return

            request = b""
            while b"\r\n\r\n" not in request:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                request += chunk

            conn.sendall(self.response_data)

        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


class MockSOCKS5Client:
    def __init__(self, proxy_host: str, proxy_port: int):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.sock: Optional[socket.socket] = None

    def connect(self, target_host: str, target_port: int) -> socket.socket:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.proxy_host, self.proxy_port))

        self.sock.sendall(b"\x05\x01\x00")
        response = self.sock.recv(2)
        if response != b"\x05\x00":
            raise Exception(f"SOCKS5 auth failed: {response}")

        host_bytes = target_host.encode() if isinstance(target_host, str) else target_host
        request = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + socket.inet_aton(str(target_port)).rjust(4, b'\x00')[-4:]
        self.sock.sendall(request)

        response = self.sock.recv(10)
        if len(response) < 10 or response[0] != 5 or response[1] != 0:
            raise Exception(f"SOCKS5 connect failed: {response}")

        return self.sock

    def send_http_request(self, method: str = "GET", path: str = "/", headers: dict = None, body: bytes = b""):
        if not self.sock:
            raise Exception("Not connected")

        request_headers = headers or {}
        request = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
        for key, value in request_headers.items():
            request += f"{key}: {value}\r\n"
        if body:
            request += f"Content-Length: {len(body)}\r\n"
        request += "\r\n"
        self.sock.sendall(request.encode() + body)

    def recv_response(self, size: int = 8192) -> bytes:
        if not self.sock:
            raise Exception("Not connected")
        return self.sock.recv(size)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None