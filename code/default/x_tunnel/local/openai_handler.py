import random
import json
import base64
import time
import zlib

import utils

from .context import ctx
from . import front_dispatcher
from . import api_client

from log_buffer import getLogger
xlog = getLogger("x_tunnel")

openai_chat_token_price = 0.000002

gzip_decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)


def get_auth_str():
    info = {
        "login_account": ctx.config.login_account,
        "login_password": ctx.config.login_password
    }
    json_str = utils.to_bytes(json.dumps(info))
    token = base64.b64encode(json_str)
    return "Bearer " + utils.to_str(token)


def get_openai_proxy(get_next_one=False):
    if get_next_one or not ctx.openai_proxy_host:

        if not (ctx.config.login_account and ctx.config.login_password):
            return False

        for _ in range(0, 3):
            res, reason = api_client.request_balance(ctx.config.login_account, ctx.config.login_password)
            if not res:
                xlog.warn("x-tunnel request_balance fail when create_conn:%s", reason)
                time.sleep(1)

        if not ctx.openai_proxies:
            return None

        ctx.openai_proxy_host = random.choice(ctx.openai_proxies)
    return ctx.openai_proxy_host


def handle_openai(method, path, headers, req_body, sock):
    if not ctx.openai_auth_str:
        ctx.openai_auth_str = get_auth_str()

    host = get_openai_proxy()
    if not host:
        return 401, {}, "Service not available at current status."

    path = utils.to_str(path[7:])
    headers = utils.to_str(headers)
    headers["Authorization"] = ctx.openai_auth_str
    del headers["Host"]
    try:
        del headers["Accept-Encoding"]
    except Exception:
        pass
    content, status, response = front_dispatcher.request(method, host, path=path, headers=headers, data=req_body)

    if status == 200:
        try:
            if response.headers.get(b"Content-Encoding") == b"gzip":
                data = gzip_decompressor.decompress(content)
            else:
                data = content

            dat = json.loads(data)
            consumed_balance = dat["usage"]["consumed_balance"]
            ctx.openai_balance -= consumed_balance
        except Exception as e1:
            xlog.exception("cal tokens err:%r", e1)

    res_headers = {
        "Content-Type": "application/json"
    }
    for key, value in response.headers.items():
        if key.startswith(b"Openai"):
            res_headers[key] = value

    return status, res_headers, content
