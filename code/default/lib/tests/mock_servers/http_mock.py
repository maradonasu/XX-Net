#!/usr/bin/env python3
# coding:utf-8

import socket
from typing import Optional
from mock_servers import MockServerBase

class HTTPMockServer(MockServerBase):
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        super().__init__(host, port)
        self.response_status = 200
        self.response_body = b"OK"
        self.response_headers = {"Content-Type": "text/plain", "Connection": "close"}
        self._custom_handler: Optional[callable] = None

    def set_response(self, status: int = 200, body: bytes = b"OK", headers: dict = None):
        self.response_status = status
        self.response_body = body
        if headers:
            self.response_headers = headers

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

            header_lines = request.split(b"\r\n\r\n")[0].split(b"\r\n")
            method, path, _ = header_lines[0].split(b" ", 2)

            content_length = 0
            for line in header_lines[1:]:
                if line.lower().startswith(b"content-length:"):
                    content_length = int(line.split(b":")[1].strip())

            body_received = request.split(b"\r\n\r\n")[1]
            while len(body_received) < content_length:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                body_received += chunk

            response_headers_str = ""
            for key, value in self.response_headers.items():
                response_headers_str += f"{key}: {value}\r\n"

            response = f"HTTP/1.1 {self.response_status} OK\r\n{response_headers_str}Content-Length: {len(self.response_body)}\r\n\r\n".encode()
            response += self.response_body
            conn.sendall(response)

        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass