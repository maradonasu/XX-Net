#!/usr/bin/env python3
# coding:utf-8
"""
HTTP Server using stdlib socketserver and http.server.

This module provides a threading HTTP server compatible with the previous
simple_http_server interface, allowing gradual migration without breaking
existing code.
"""

from __future__ import annotations

import os
import socket
import threading
import datetime
import time
import json
import errno
import base64
import hashlib
import struct
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn, TCPServer
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import utils
from xlog import getLogger
xlog = getLogger("http_server")


class GetReqTimeout(Exception):
    pass


class ParseReqFail(Exception):
    def __init__(self, message: str) -> None:
        self.message = message

    def __str__(self) -> str:
        return repr(self.message)

    def __repr__(self) -> str:
        return repr(self.message)


class HttpServerHandler(BaseHTTPRequestHandler):
    WebSocket_MAGIC_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    default_request_version = "HTTP/1.1"
    protocol_version = "HTTP/1.1"
    
    rbufsize = 32 * 1024
    wbufsize = 32 * 1024
    
    res_headers: Dict[str, str] = {}
    
    def __init__(self, sock: socket.socket, client: Tuple[str, int], 
                 args: Any, logger: Optional[Any] = None) -> None:
        self.connection = sock
        self.client_address = client
        self.args = args
        if logger:
            self.logger = logger
        else:
            self.logger = xlog
        
        self.rfile = self.connection.makefile('rb', self.rbufsize)
        self.wfile = self.connection.makefile('wb', self.wbufsize)
        self.close_connection = 0
        self.command = ""
        self.path = ""
        self.headers: Dict[bytes, bytes] = {}
        self.setup()

    def setup(self) -> None:
        pass

    def finish(self) -> None:
        try:
            self.connection.close()
        except Exception:
            pass

    def address_string(self) -> str:
        return '%s:%s' % self.client_address[:2]

    def set_CORS(self, headers: Dict[str, str]) -> None:
        self.res_headers = headers

    def parse_headers(self) -> Dict[bytes, bytes]:
        headers: Dict[bytes, bytes] = {}
        while True:
            line = self.rfile.readline(65537)
            line = line.strip()
            if len(line) == 0:
                break
            k, v = line.split(b":", 1)
            key = k.title()
            headers[key] = v.lstrip()
        return headers

    def parse_request(self) -> bool:
        try:
            self.raw_requestline = self.rfile.readline(65537)
        except Exception:
            raise GetReqTimeout()

        if not self.raw_requestline:
            raise GetReqTimeout()

        if len(self.raw_requestline) > 65536:
            raise ParseReqFail("Recv command line too large")

        line_str = self.raw_requestline.decode('iso-8859-1', errors='ignore')
        if len(line_str) > 0 and line_str[0] == '\x16':
            raise socket.error("TLS handshake on non-TLS port")

        self.command = ''
        self.path = ''
        self.request_version = self.default_request_version

        requestline = self.raw_requestline.rstrip(b'\r\n')
        self.requestline = requestline
        words = requestline.split()
        if len(words) == 3:
            command, path, version = words
            if version[:5] != b'HTTP/':
                raise ParseReqFail("Req command format fail:%s" % requestline)
            try:
                base_version_number = version.split(b'/', 1)[1]
                version_number = base_version_number.split(b".")
                if len(version_number) != 2:
                    raise ParseReqFail("Req command format fail:%s" % requestline)
                version_number = int(version_number[0]), int(version_number[1])
            except (ValueError, IndexError):
                raise ParseReqFail("Req command format fail:%s" % requestline)
            if version_number >= (1, 1):
                self.close_connection = 0
            if version_number >= (2, 0):
                raise ParseReqFail("Req command format fail:%s" % requestline)
        elif len(words) == 2:
            command, path = words
            self.close_connection = 1
            if command != b'GET':
                raise ParseReqFail("Req command format HTTP/0.9 line:%s" % requestline)
        elif not words:
            raise ParseReqFail("Req command format fail:%s" % requestline)
        else:
            raise ParseReqFail("Req command format fail:%s" % requestline)
        
        self.command = command.decode('iso-8859-1')
        self.path_bytes = path
        self.path = path.decode('iso-8859-1', errors='ignore')
        
        self.headers = self.parse_headers()
        
        self.host = self.headers.get(b'Host', b"")
        conntype = self.headers.get(b'Connection', b"")
        if conntype.lower() == b'close':
            self.close_connection = 1
        elif conntype.lower() == b'keep-alive':
            self.close_connection = 0
        
        self.upgrade = self.headers.get(b'Upgrade', b"").lower()
        
        return True

    def unpack_reqs(self, reqs: Dict[bytes, List[bytes]]) -> Dict[str, str]:
        query: Dict[str, str] = {}
        for key, val1 in reqs.items():
            key_str = key.decode('iso-8859-1', errors='ignore')
            if isinstance(val1, list):
                query[key_str] = val1[0].decode('iso-8859-1', errors='ignore')
            else:
                query[key_str] = val1.decode('iso-8859-1', errors='ignore')
        return query

    def handle_one_request(self) -> None:
        try:
            self.parse_request()
            self.close_connection = 0
            
            if self.upgrade == b"websocket":
                self.do_WebSocket()
            elif self.command == "GET":
                self.do_GET()
            elif self.command == "POST":
                self.do_POST()
            elif self.command == "CONNECT":
                self.do_CONNECT()
            elif self.command == "HEAD":
                self.do_HEAD()
            elif self.command == "DELETE":
                self.do_DELETE()
            elif self.command == "OPTIONS":
                self.do_OPTIONS()
            elif self.command == "PUT":
                self.do_PUT()
            else:
                self.logger.warn("unhandler cmd:%s path:%s from:%s", 
                                 self.command, self.path, self.address_string())
                return
            
            self.wfile.flush()
        except ParseReqFail as e:
            self.logger.warn("parse req except:%r", e)
            self.close_connection = 1
        except socket.error as e:
            self.logger.warn("socket error:%r", e)
            self.close_connection = 1
        except IOError as e:
            if hasattr(e, 'errno') and e.errno == errno.EPIPE:
                pass
            else:
                self.logger.warn("IOError:%r", e)
            self.close_connection = 1
        except GetReqTimeout:
            self.close_connection = 1
        except Exception as e:
            self.logger.exception("handler:%r cmd:%s path:%s from:%s", 
                                  e, self.command, self.path, self.address_string())
            self.close_connection = 1

    def handle(self) -> None:
        while True:
            try:
                self.close_connection = 1
                self.handle_one_request()
            except Exception as e:
                self.logger.warn("handle err:%r close", e)
                self.close_connection = 1
            
            if self.close_connection:
                break
        self.connection.close()

    def WebSocket_handshake(self) -> bool:
        protocol = self.headers.get(b"Sec-WebSocket-Protocol", b"")
        if protocol:
            self.logger.info("Sec-WebSocket-Protocol:%s", protocol)
        version = self.headers.get(b"Sec-WebSocket-Version", b"")
        if version != b"13":
            self.logger.warn("Sec-WebSocket-Version:%s", version)
            self.close_connection = 1
            return False
        
        key = self.headers[b"Sec-WebSocket-Key"]
        self.WebSocket_key = key
        digest = base64.b64encode(hashlib.sha1(key + self.WebSocket_MAGIC_GUID).digest())
        response = b'HTTP/1.1 101 Switching Protocols\r\n'
        response += b'Upgrade: websocket\r\n'
        response += b'Connection: Upgrade\r\n'
        response += b'Sec-WebSocket-Accept: %s\r\n\r\n' % digest
        self.wfile.write(response)
        return True

    def WebSocket_send_message(self, message: bytes) -> None:
        self.wfile.write(bytes([129]))
        length = len(message)
        if length <= 125:
            self.wfile.write(bytes([length]))
        elif length >= 126 and length <= 65535:
            self.wfile.write(bytes([126]))
            self.wfile.write(struct.pack(">H", length))
        else:
            self.wfile.write(bytes([127]))
            self.wfile.write(struct.pack(">Q", length))
        self.wfile.write(message)

    def WebSocket_receive_worker(self) -> None:
        while not self.close_connection:
            try:
                h = self.rfile.read(2)
                if h is None or len(h) == 0:
                    break
                length = h[1] & 127
                if length == 126:
                    length = struct.unpack(">H", self.rfile.read(2))[0]
                elif length == 127:
                    length = struct.unpack(">Q", self.rfile.read(8))[0]
                masks = list(self.rfile.read(4))
                decoded = bytearray()
                for char in self.rfile.read(length):
                    decoded.append(char ^ masks[len(decoded) % 4])
                try:
                    self.WebSocket_on_message(bytes(decoded))
                except Exception as e:
                    self.logger.warn("WebSocket %s except on process message, %r", 
                                     self.WebSocket_key, e)
            except Exception as e:
                self.logger.exception("WebSocket %s exception:%r", self.WebSocket_key, e)
                break
        
        self.WebSocket_on_close()
        self.close_connection = 1

    def WebSocket_on_message(self, message: bytes) -> None:
        self.logger.debug("websocket message:%s", message)

    def WebSocket_on_close(self) -> None:
        self.logger.debug("websocket closed")

    def do_WebSocket(self) -> None:
        self.logger.info("WebSocket cmd:%s path:%s from:%s", 
                         self.command, self.path, self.address_string())
        self.logger.info("Host:%s", self.headers.get(b"Host", b""))
        
        if not self.WebSocket_on_connect():
            return
        
        if not self.WebSocket_handshake():
            self.logger.warn("WebSocket handshake fail.")
            return
        
        self.WebSocket_receive_worker()

    def WebSocket_on_connect(self) -> bool:
        self.logger.warn("unhandled WebSocket from %s", self.address_string())
        self.send_error(501, "Not supported")
        self.close_connection = 1
        return False

    def do_GET(self) -> None:
        self.logger.warn("unhandler cmd:%s from:%s", self.command, self.address_string())

    def do_POST(self) -> None:
        self.logger.warn("unhandler cmd:%s from:%s", self.command, self.address_string())

    def do_PUT(self) -> None:
        self.logger.warn("unhandler cmd:%s from:%s", self.command, self.address_string())

    def do_DELETE(self) -> None:
        self.logger.warn("unhandler cmd:%s from:%s", self.command, self.address_string())

    def do_OPTIONS(self) -> None:
        self.logger.warn("unhandler cmd:%s from:%s", self.command, self.address_string())

    def do_HEAD(self) -> None:
        self.logger.warn("unhandler cmd:%s from:%s", self.command, self.address_string())

    def do_CONNECT(self) -> None:
        self.logger.warn("unhandler cmd:%s from:%s", self.command, self.address_string())

    def send_not_found(self) -> None:
        self.close_connection = 1
        content = b"File not found."
        self.wfile.write(b'HTTP/1.1 404\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s' % (len(content), content))

    def send_error(self, code: int, message: Optional[str] = None) -> None:
        self.close_connection = 1
        self.wfile.write(b'HTTP/1.1 %d\r\n' % code)
        self.wfile.write(b'Connection: close\r\n\r\n')
        if message:
            self.wfile.write(utils.to_bytes(message))

    def send_response(self, mimetype: Union[str, bytes] = "", content: Union[str, bytes] = "",
                      headers: Union[Dict, str, bytes] = "", status: int = 200) -> None:
        data: List[bytes] = []
        data.append(b'HTTP/1.1 %d\r\n' % status)
        if len(mimetype):
            data.append(b'Content-Type: %s\r\n' % utils.to_bytes(mimetype))
        
        content_bytes = utils.to_bytes(content)
        
        for key in self.res_headers:
            data.append(b"%s: %s\r\n" % (utils.to_bytes(key), utils.to_bytes(self.res_headers[key])))
        data.append(b'Content-Length: %d\r\n' % len(content_bytes))
        
        if len(headers):
            if isinstance(headers, dict):
                headers_bytes = utils.to_bytes(headers)
                if b'Content-Length' in headers_bytes:
                    del headers_bytes[b'Content-Length']
                for key in headers_bytes:
                    data.append(b"%s: %s\r\n" % (utils.to_bytes(key), utils.to_bytes(headers_bytes[key])))
            elif isinstance(headers, str):
                data.append(headers.encode("utf-8"))
            elif isinstance(headers, bytes):
                data.append(headers)
        data.append(b"\r\n")
        
        if len(content_bytes) < 1024:
            data.append(content_bytes)
            data_str = b"".join(data)
            self.wfile.write(data_str)
        else:
            data_str = b"".join(data)
            self.wfile.write(data_str)
            if len(content_bytes):
                self.wfile.write(content_bytes)

    def send_redirect(self, url: Union[str, bytes], headers: Dict = {}, 
                      content: Union[str, bytes] = b"", status: int = 307,
                      text: Union[str, bytes] = b"Temporary Redirect") -> None:
        url_bytes = utils.to_bytes(url)
        headers_bytes = utils.to_bytes(headers)
        content_bytes = utils.to_bytes(content)
        
        headers_bytes[b"Location"] = url_bytes
        data: List[bytes] = []
        data.append(b'HTTP/1.1 %d\r\n' % status)
        data.append(b'Content-Length: %s\r\n' % len(content_bytes))
        
        if len(headers_bytes):
            for key in headers_bytes:
                data.append(b"%s: %s\r\n" % (key, headers_bytes[key]))
        data.append(b"\r\n")
        data.append(content_bytes)
        data_str = b"".join(data)
        self.wfile.write(data_str)

    def send_response_nc(self, mimetype: Union[str, bytes] = "", content: Union[str, bytes] = "",
                          headers: Union[Dict, str, bytes] = "", status: int = 200) -> None:
        no_cache_headers = b"Cache-Control: no-cache, no-store, must-revalidate\r\nPragma: no-cache\r\nExpires: 0\r\n"
        return self.send_response(mimetype, content, no_cache_headers + headers, status)

    def send_file(self, filename: str, mimetype: Union[str, bytes]) -> None:
        try:
            if not os.path.isfile(filename):
                self.send_not_found()
                return
            
            file_size = os.path.getsize(filename)
            tme = (datetime.datetime.today() + datetime.timedelta(minutes=0)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            head = b'HTTP/1.1 200\r\nAccess-Control-Allow-Origin: *\r\nCache-Control:no-cache\r\n'
            head += b'Expires: %s\r\nContent-Type: %s\r\nContent-Length: %s\r\n\r\n' % utils.to_bytes(
                (tme, mimetype, file_size))
            self.wfile.write(head)
            
            with open(filename, 'rb') as fp:
                while True:
                    data = fp.read(65535)
                    if not data:
                        break
                    self.wfile.write(data)
        except Exception:
            pass

    def response_json(self, res_arr: Any, headers: Union[Dict, str, bytes] = "") -> None:
        data = json.dumps(utils.to_str(res_arr), indent=0, sort_keys=True)
        self.send_response(b'application/json', data, headers=headers)


class ThreadedHTTPServer(ThreadingMixIn, TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    
    def __init__(self, server_address: Tuple[str, int], 
                 RequestHandlerClass: Callable, 
                 args: Any = (), logger: Any = xlog, max_thread: int = 1024,
                 check_listen_interval: Optional[float] = None) -> None:
        TCPServer.__init__(self, server_address, RequestHandlerClass)
        self.args = args
        self.logger = logger
        self.max_thread = max_thread
        self.check_listen_interval = check_listen_interval
        self.running = False
        self.sockets: List[socket.socket] = []
        self.http_thread: Optional[threading.Thread] = None
    
    def process_request(self, request: socket.socket, client_address: Tuple[str, int]) -> None:
        if threading.active_count() > self.max_thread:
            self.logger.warn("thread num exceed the limit. drop request from %s.", client_address)
            request.close()
            return
        
        t = threading.Thread(target=self.process_request_thread,
                             args=(request, client_address),
                             name="handle_%s:%d" % client_address)
        t.daemon = True
        t.start()
    
    def process_request_thread(self, request: socket.socket, client_address: Tuple[str, int]) -> None:
        try:
            try:
                handler = self.RequestHandlerClass(request, client_address, self.args, self.logger)
            except TypeError:
                handler = self.RequestHandlerClass(request, client_address, self.args)
            handler.handle()
        except Exception as e:
            self.logger.exception("process_request_thread error:%r", e)
        finally:
            request.close()


class HTTPServer:
    def __init__(self, addresses: Union[Tuple[Union[str, bytes], int], List[Tuple[Union[str, bytes], int]]],
                 handler: Callable, args: Any = (), use_https: bool = False,
                 cert: str = "", logger: Any = xlog, max_thread: int = 1024,
                 check_listen_interval: Optional[float] = None) -> None:
        self.servers: List[ThreadedHTTPServer] = []
        if isinstance(addresses, tuple):
            addresses = [addresses]
        
        self.addresses = []
        for addr in addresses:
            ip, port = addr
            if isinstance(ip, bytes):
                ip = ip.decode('ascii', errors='ignore')
            self.addresses.append((ip, port))
        
        self.handler = handler
        self.logger = logger
        self.args = args
        self.use_https = use_https
        self.cert = cert
        self.max_thread = max_thread
        self.check_listen_interval = check_listen_interval
        self.running = False
        self.sockets: List[socket.socket] = []
    
    def init_socket(self) -> None:
        for addr in self.addresses:
            try:
                server = ThreadedHTTPServer(addr, self.handler, self.args, 
                                          self.logger, self.max_thread,
                                          self.check_listen_interval)
                self.servers.append(server)
                self.sockets.append(server.socket)
                self.logger.info("server %s:%d started.", addr[0], addr[1])
            except Exception as e:
                self.logger.error("bind to %s:%d fail:%r", addr[0], addr[1], e)
                raise
    
    def serve_forever(self) -> None:
        if not self.servers:
            self.init_socket()
        
        self.running = True
        for server in self.servers:
            t = threading.Thread(target=server.serve_forever, 
                                 name="serve_%s:%d" % server.server_address)
            t.daemon = True
            t.start()
        
        while self.running:
            time.sleep(1)
    
    def start(self) -> None:
        self.init_socket()
        self.running = True
        for server in self.servers:
            t = threading.Thread(target=server.serve_forever, 
                                 name="serve_%s:%d" % server.server_address)
            t.daemon = True
            t.start()
    
    def shutdown(self) -> None:
        self.running = False
        for server in self.servers:
            server.shutdown()
            server.server_close()
        self.servers = []
        self.logger.info("shutdown")
    
    def server_close(self) -> None:
        for server in self.servers:
            server.server_close()
        self.servers = []


class TestHttpServer(HttpServerHandler):
    def __init__(self, sock: socket.socket, client: Tuple[str, int], args: Any, 
                 logger: Optional[Any] = None) -> None:
        self.data_path = utils.to_bytes(args) if args else b""
        if logger is None:
            logger = xlog
        HttpServerHandler.__init__(self, sock, client, args, logger)

    def generate_random_lowercase(self, n: int) -> bytearray:
        min_lc = ord('a')
        len_lc = 26
        ba = bytearray(os.urandom(n))
        for i, b in enumerate(ba):
            ba[i] = min_lc + b % len_lc
        return ba

    def WebSocket_on_connect(self) -> bool:
        return True

    def WebSocket_on_message(self, message: bytes) -> None:
        self.WebSocket_send_message(message)

    def do_GET(self) -> None:
        url_path = urlparse(self.path).path
        req = urlparse(self.path).query
        reqs = parse_qs(req, keep_blank_values=True)
        
        self.logger.debug("GET %s from %s:%d", self.path, self.client_address[0], self.client_address[1])
        
        if url_path == "/test":
            tme = (datetime.datetime.today() + datetime.timedelta(minutes=330)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            tme = utils.to_bytes(tme)
            head = b'HTTP/1.1 200\r\nAccess-Control-Allow-Origin: *\r\nCache-Control:public, max-age=31536000\r\n'
            head += b'Expires: %s\r\nContent-Type: text/plain\r\nContent-Length: 4\r\n\r\nOK\r\n' % (tme)
            self.wfile.write(head)
        elif url_path == '/':
            data = b"OK\r\n"
            self.wfile.write(b'HTTP/1.1 200\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: %d\r\n\r\n%s' % (len(data), data))
        elif url_path == '/null':
            mimetype = b"application/x-binary"
            if b"size" in reqs:
                file_size = int(reqs[b'size'][0])
            else:
                file_size = 1024 * 1024 * 1024
            
            self.wfile.write(b'HTTP/1.1 200\r\nContent-Type: %s\r\nContent-Length: %s\r\n\r\n' % (mimetype, file_size))
            start = 0
            data = self.generate_random_lowercase(65535)
            while start < file_size:
                left = file_size - start
                send_batch = min(left, 65535)
                self.wfile.write(bytes(data[:send_batch]))
                start += send_batch
        else:
            if b".." in url_path[1:]:
                return self.send_not_found()
            
            target = os.path.join(self.data_path, url_path[1:])
            if os.path.isfile(target):
                self.send_file(target, b"application/x-binary")
            else:
                self.wfile.write(b'HTTP/1.1 404\r\nContent-Length: 0\r\n\r\n')


def main(data_path: str = ".") -> None:
    xlog.info("listen http on 8880")
    httpd = HTTPServer(('', 8880), TestHttpServer, data_path)
    httpd.start()
    
    while True:
        time.sleep(10)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        data_path = sys.argv[1]
    else:
        data_path = ""
    
    try:
        main(data_path=data_path)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
    except KeyboardInterrupt:
        sys.exit()