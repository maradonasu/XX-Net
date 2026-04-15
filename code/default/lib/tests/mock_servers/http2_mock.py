#!/usr/bin/env python3
# coding:utf-8

import socket
import ssl
from typing import Optional
from h2.connection import H2Connection
from h2.events import RequestReceived, DataReceived, StreamEnded
from h2.config import H2Configuration
from mock_servers import MockServerBase

class HTTP2MockServer(MockServerBase):
    def __init__(self, host: str = "127.0.0.1", port: int = 0, use_ssl: bool = True):
        super().__init__(host, port)
        self.use_ssl = use_ssl
        self.ssl_context: Optional[ssl.SSLContext] = None
        self.response_status = 200
        self.response_body = b"OK"
        self.response_headers = {"content-type": "text/plain"}
        self._custom_handler: Optional[callable] = None

        if use_ssl:
            self._setup_ssl()

    def _setup_ssl(self):
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1

    def set_response(self, status: int = 200, body: bytes = b"OK", headers: dict = None):
        self.response_status = status
        self.response_body = body
        if headers:
            self.response_headers = headers

    def set_custom_handler(self, handler: callable):
        self._custom_handler = handler

    def _handle_connection(self, conn: socket.socket, addr: tuple):
        try:
            if self.use_ssl and self.ssl_context:
                try:
                    conn = self.ssl_context.wrap_socket(conn, server_side=True)
                except ssl.SSLError:
                    return

            if self._custom_handler:
                self._custom_handler(conn, addr)
                return

            config = H2Configuration(client_side=False)
            h2_conn = H2Connection(config=config)
            h2_conn.initiate_connection()
            conn.sendall(h2_conn.data_to_send())

            stream_id = None
            request_data = b""

            while True:
                data = conn.recv(65535)
                if not data:
                    break

                events = h2_conn.receive_data(data)
                for event in events:
                    if isinstance(event, RequestReceived):
                        stream_id = event.stream_id
                        headers = dict(event.headers)
                    elif isinstance(event, DataReceived):
                        request_data += event.data
                        h2_conn.acknowledge_received_data(event.data, event.stream_id)
                    elif isinstance(event, StreamEnded):
                        if stream_id is not None:
                            response_headers = [
                                (":status", str(self.response_status)),
                            ]
                            for key, value in self.response_headers.items():
                                response_headers.append((key.encode() if isinstance(key, str) else key, 
                                                         value.encode() if isinstance(value, str) else value))

                            h2_conn.send_headers(stream_id, response_headers)
                            h2_conn.send_data(stream_id, self.response_body, end_stream=True)
                            conn.sendall(h2_conn.data_to_send())
                            return

                conn.sendall(h2_conn.data_to_send())

        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass