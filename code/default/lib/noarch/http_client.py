#!/usr/bin/env python3
# coding:utf-8

import os
import time
from urllib.parse import urlsplit

from log_buffer import getLogger
xlog = getLogger("http_client")

import httpx
import utils

from http_response_parser import BaseResponse


def _build_proxy_url(proxy_dict):
    if not proxy_dict:
        return None
    if isinstance(proxy_dict, str):
        return proxy_dict

    scheme = proxy_dict.get("type", "http")
    host = proxy_dict.get("host", "")
    port = proxy_dict.get("port", "")
    user = proxy_dict.get("user")
    password = proxy_dict.get("pass")

    netloc = ""
    if user and password:
        netloc = f"{user}:{password}@"
    netloc += host
    if port:
        netloc += f":{port}"

    return f"{scheme}://{netloc}"


class Client(object):
    def __init__(self, proxy=None, timeout=60, cert=""):
        self.timeout = timeout
        self.cert = cert
        self.sock = None
        self.host = None
        self.port = None
        self.tls = None
        self.ssl_context = None

        if isinstance(proxy, str):
            proxy_sp = urlsplit(proxy)

            self.proxy = {
                "type": proxy_sp.scheme,
                "host": proxy_sp.hostname,
                "port": proxy_sp.port,
                "user": proxy_sp.username,
                "pass": proxy_sp.password
            }
        elif isinstance(proxy, dict):
            self.proxy = proxy
        else:
            self.proxy = None

        self._httpx_client = None

    def _get_httpx_client(self):
        if self._httpx_client is not None:
            return self._httpx_client

        proxy_url = _build_proxy_url(self.proxy)
        verify = True
        if self.cert:
            if os.path.isfile(self.cert):
                verify = self.cert

        self._httpx_client = httpx.Client(
            proxy=proxy_url,
            timeout=self.timeout,
            verify=verify,
            follow_redirects=False,
        )
        return self._httpx_client

    def request(self, method, url, headers=None, body=b"", read_payload=True):
        if headers is None:
            headers = {}
        url = utils.to_str(url)
        method = utils.to_str(method).upper()

        if isinstance(body, (bytes, bytearray, memoryview)):
            content = bytes(body) if body else b""
        elif isinstance(body, str):
            content = body.encode("utf-8")
        else:
            content = b""

        try:
            client = self._get_httpx_client()
            resp = client.request(
                method=method,
                url=url,
                headers=headers,
                content=content,
            )
        except httpx.TimeoutException:
            xlog.debug("httpx request %s timeout", url)
            return None
        except httpx.ConnectError as e:
            xlog.warn("httpx connect %s fail:%r", url, e)
            return None
        except Exception as e:
            xlog.warn("httpx request %s fail:%r", url, e)
            return None

        response = BaseResponse(
            status=resp.status_code,
            reason=resp.reason_phrase.encode("utf-8") if resp.reason_phrase else b"",
            headers={},
        )

        for key, value in resp.headers.multi_items():
            response.headers[key.title()] = value.encode("utf-8") if isinstance(value, str) else value

        if read_payload:
            response.text = resp.content
        else:
            response.text = b""

        return response


def request(method="GET", url=None, headers=None, body=b"", proxy=None, timeout=60, read_payload=True):
    if headers is None:
        headers = {}
    if not url:
        raise Exception("no url")

    client = Client(proxy, timeout=timeout)
    return client.request(method, url, headers, body, read_payload)
