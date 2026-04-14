from __future__ import annotations

import socket
import struct
import time
from typing import Any, Callable, Dict, List, Optional, Union

import socks
import utils
from . import openssl_wrap
from subj_alt_name import SubjectAltName
from pyasn1.codec.der import decoder as der_decoder


class ConnectCreator(object):
    def __init__(self, logger: Any, config: Any, openssl_context: Optional[Any] = None,
                 host_manager: Optional[Any] = None, timeout: int = 5, debug: bool = False,
                 check_cert: Optional[Callable[[Any], None]] = None) -> None:
        self.logger: Any = logger
        self.config: Any = config
        self.openssl_context: Optional[Any] = openssl_context
        self.host_manager: Optional[Any] = host_manager
        self.timeout: int = self.config.socket_timeout
        self.debug: bool = debug or self.config.show_state_debug
        self.peer_cert: Optional[Dict[str, Any]] = None
        if check_cert:
            self.check_cert = check_cert
        self.update_config()

        self.connect_force_http1: bool = self.config.connect_force_http1
        self.connect_force_http2: bool = self.config.connect_force_http2

    def update_config(self) -> None:
        if int(self.config.PROXY_ENABLE):

            if self.config.PROXY_TYPE == "HTTP":
                proxy_type = socks.HTTP
            elif self.config.PROXY_TYPE == "SOCKS4":
                proxy_type = socks.SOCKS4
            elif self.config.PROXY_TYPE == "SOCKS5":
                proxy_type = socks.SOCKS5
            else:
                self.logger.error("proxy type %s unknown, disable proxy", self.config.PROXY_TYPE)
                raise Exception()

            socks.set_default_proxy(proxy_type=proxy_type,
                                    addr=self.config.PROXY_HOST,
                                    port=self.config.PROXY_PORT,
                                    username=self.config.PROXY_USER,
                                    password=self.config.PROXY_PASSWD)

    def connect_ssl(self, ip_str: Union[str, bytes], sni: Union[str, bytes], host: str,
                    close_cb: Optional[Callable[[], None]] = None) -> Any:
        ip_str = utils.to_str(ip_str)

        if self.debug:
            self.logger.debug("connect ip:%s sni:%s host:%s", ip_str, sni, host)

        ip, port = utils.get_ip_port(ip_str)
        ip_text = utils.to_str(ip)

        if openssl_wrap.implementation == "UTLS":
            # currently UTLS will create TLS connection by itself.
            # So will not support LAN proxy.
            sock = None
        else:
            family = socket.AF_INET6 if ":" in ip_text else socket.AF_INET
            if int(self.config.PROXY_ENABLE):
                sock = socks.socksocket(family)
            else:
                sock = socket.socket(family)

            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # set struct linger{l_onoff=1,l_linger=0} to avoid 10048 socket error
            # Close the connection with a TCP RST instead of a TCP FIN.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))

            # resize socket receive buffer ->64 above to improve browser related application performance
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.config.connect_receive_buffer)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.config.connect_send_buffer)
            sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, True)
            sock.settimeout(self.timeout)

        time_begin = time.time()
        ssl_sock = openssl_wrap.SSLConnection(self.openssl_context.context, sock,
                                              ip_str=ip_str,
                                              sni=sni,
                                              on_close=close_cb)

        ssl_sock.sni = utils.to_str(sni)

        time_connected = time.time()

        try:
            ssl_sock.do_handshake()
        except Exception as e:
            # self.logger.exception("handshake except:%r", e)
            raise socket.error('tls handshake fail, sni:%s, top:%s e:%r' % (sni, host, e))

        if ssl_sock.is_support_h2():
            ssl_sock.h2 = True
        else:
            ssl_sock.h2 = False

        time_handshaked = time.time()

        self.check_cert(ssl_sock)

        connect_time = int((time_connected - time_begin) * 1000)
        handshake_time = int((time_handshaked - time_begin) * 1000)
        if sock:
            ssl_sock.fd = sock.fileno()
        ssl_sock.create_time = time_begin
        ssl_sock.connect_time = connect_time
        ssl_sock.handshake_time = handshake_time
        ssl_sock.last_use_time = time_handshaked
        ssl_sock.host = host
        ssl_sock.received_size = 0

        return ssl_sock

    def check_cert(self, ssl_sock: Any) -> None:
        try:
            peer_cert = ssl_sock.get_cert()
        except Exception as e:
            self.logger.exception("check_cert %r", e)

        if self.debug:
            self.logger.debug("cert:%r", peer_cert)

        if self.config.check_commonname:
            if not peer_cert["issuer_commonname"].startswith(self.config.check_commonname):
                raise socket.error(' certificate is issued by %r' % (peer_cert["issuer_commonname"]))

        if isinstance(self.config.check_sni, str):
            if self.config.check_sni not in peer_cert["altName"]:
                raise socket.error(
                    'check sni fail:%s, alt_names:%s' % (self.config.check_sni, peer_cert["altName"]))

        elif self.config.check_sni:
            alt_name = peer_cert["altName"]
            if isinstance(alt_name, str):
                if not ssl_sock.sni.endswith(alt_name):
                    raise socket.error(
                        'check %s sni:%s fail, alt_names:%s' % (ssl_sock.ip_str, ssl_sock.sni, alt_name))
            elif isinstance(alt_name, list):
                for alt_name_n in alt_name:
                    if ssl_sock.sni.endswith(alt_name_n):
                        return
                raise socket.error(
                    'check %s sni:%s fail, alt_names:%s' % (ssl_sock.ip_str, ssl_sock.sni, alt_name))

    def get_ssl_cert_domain(self, ssl_sock: Any) -> None:
        cert = ssl_sock.get_peer_certificate()
        if not cert:
            raise Exception("no cert")

        ssl_cert = openssl_wrap.SSLCert(cert)
        ssl_sock.domain = ssl_cert.cn

    @staticmethod
    def get_subj_alt_name(peer_cert: Any) -> List[str]:
        '''
        Copied from ndg.httpsclient.ssl_peer_verification.ServerSSLCertVerification
        Extract subjectAltName DNS name settings from certificate extensions
        @param peer_cert: peer certificate in SSL connection.  subjectAltName
        settings if any will be extracted from this
        @type peer_cert: OpenSSL.crypto.X509
        '''
        # Search through extensions
        dns_name = []
        general_names = SubjectAltName()
        for i in range(peer_cert.get_extension_count()):
            ext = peer_cert.get_extension(i)
            ext_name = ext.get_short_name()
            if ext_name == "subjectAltName":
                # PyOpenSSL returns extension data in ASN.1 encoded form
                ext_dat = ext.get_data()
                decoded_dat = der_decoder.decode(ext_dat, asn1Spec=general_names)

                for name in decoded_dat:
                    if isinstance(name, SubjectAltName):
                        for entry in range(len(name)):
                            component = name.getComponentByPosition(entry)
                            n = str(component.getComponent())
                            if n.startswith("*"):
                                continue
                            dns_name.append(n)
        return dns_name
