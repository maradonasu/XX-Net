#!/usr/bin/env python3
# coding:utf-8

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, Optional, Tuple, Union

import utils
import encrypt
from log_buffer import getLogger
xlog = getLogger("x_tunnel")

from .context import ctx

current_path = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.abspath(os.path.join(current_path, os.pardir, os.pardir))


def encrypt_data(data: Union[bytes, bytearray]) -> bytes:
    if ctx.config and ctx.config.encrypt_data:
        return encrypt.Encryptor(ctx.config.encrypt_password, ctx.config.encrypt_method).encrypt(data)
    return data


def decrypt_data(data: Union[bytes, memoryview]) -> bytes:
    if ctx.config and getattr(ctx.config, 'encrypt_data', None):
        if isinstance(data, memoryview):
            data = data.tobytes()
        return encrypt.Encryptor(ctx.config.encrypt_password, ctx.config.encrypt_method).decrypt(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    return data


def get_app_name() -> str:
    app_info_file = os.path.join(root_path, os.path.pardir, "app_info.json")
    try:
        with open(app_info_file, "r") as fd:
            dat = json.load(fd)
        return dat["app_name"]
    except Exception as e:
        xlog.exception("get app_name fail:%r", e)
    return "XX-Net"


def calculate_quota_left(quota_list: Dict[str, Any]) -> int:
    time_now = int(time.time())
    quota_left = 0

    try:
        if "current" in quota_list:
            c_q_end_time = quota_list["current"]["end_time"]
            if c_q_end_time > time_now:
                quota_left += quota_list["current"]["quota"]

        if "backup" in quota_list:
            for qt in quota_list["backup"]:
                b_q_quota = qt["quota"]
                b_q_end_time = qt["end_time"]
                if b_q_end_time < time_now:
                    continue
                quota_left += b_q_quota
    except Exception as e:
        xlog.exception("calculate_quota_left %s %r", quota_list, e)

    return quota_left


def call_api(path: str, req_info: Dict[str, Any]) -> Tuple[bool, Union[str, Dict[str, Any]]]:
    if not path.startswith("/"):
        path = "/" + path

    try:
        upload_post_data = json.dumps(req_info)
        upload_post_data = encrypt_data(upload_post_data)

        start_time = time.time()
        while time.time() - start_time < 30:
            content, status, response = ctx.http_client.request(
                method="POST", host=ctx.config.api_server, path=path,
                headers={"Content-Type": "application/json"},
                data=upload_post_data, timeout=5
            )
            if status >= 400:
                time.sleep(1)
                continue
            else:
                break

        time_cost = time.time() - start_time
        if status != 200:
            reason = "status:%r" % status
            xlog.warn("api:%s fail:%s t:%d", path, reason, time_cost)
            ctx.last_api_error = reason
            return False, reason

        content = decrypt_data(content)
        if isinstance(content, memoryview):
            content = content.tobytes()

        content = utils.to_str(content)
        try:
            info = json.loads(content)
        except Exception as e:
            ctx.last_api_error = "parse json fail"
            xlog.warn("api:%s parse json:%s fail:%r", path, content, e)
            return False, "parse json fail"

        res = info["res"]
        if res != "success":
            ctx.last_api_error = info["reason"]
            xlog.warn("api:%s fail:%s", path, info["reason"])
            return False, info["reason"]

        xlog.info("api:%s success t:%d", path, time_cost * 1000)
        ctx.last_api_error = ""
        return True, info
    except Exception as e:
        xlog.exception("call_api e:%r", e)
        ctx.last_api_error = "%r" % e
        return False, "except:%r" % e


async def async_call_api(path: str, req_info: Dict[str, Any]) -> Tuple[bool, Union[str, Dict[str, Any]]]:
    if not path.startswith("/"):
        path = "/" + path

    try:
        upload_post_data = json.dumps(req_info)
        upload_post_data = encrypt_data(upload_post_data)

        start_time = time.time()
        while time.time() - start_time < 30:
            loop = asyncio.get_event_loop()
            content, status, response = await loop.run_in_executor(
                None,
                lambda: ctx.http_client.request(
                    method="POST", host=ctx.config.api_server, path=path,
                    headers={"Content-Type": "application/json"},
                    data=upload_post_data, timeout=5
                )
            )
            if status >= 400:
                await asyncio.sleep(1)
                continue
            else:
                break

        time_cost = time.time() - start_time
        if status != 200:
            reason = "status:%r" % status
            xlog.warn("api:%s fail:%s t:%d", path, reason, time_cost)
            ctx.last_api_error = reason
            return False, reason

        content = decrypt_data(content)
        if isinstance(content, memoryview):
            content = content.tobytes()

        content = utils.to_str(content)
        try:
            info = json.loads(content)
        except Exception as e:
            ctx.last_api_error = "parse json fail"
            xlog.warn("api:%s parse json:%s fail:%r", path, content, e)
            return False, "parse json fail"

        res = info["res"]
        if res != "success":
            ctx.last_api_error = info["reason"]
            xlog.warn("api:%s fail:%s", path, info["reason"])
            return False, info["reason"]

        xlog.info("api:%s success t:%d", path, time_cost * 1000)
        ctx.last_api_error = ""
        return True, info
    except Exception as e:
        xlog.exception("async_call_api e:%r", e)
        ctx.last_api_error = "%r" % e
        return False, "except:%r" % e


def request_balance(
    account: Optional[str] = None,
    password: Optional[str] = None,
    is_register: bool = False,
    update_server: bool = True,
    promoter: str = ""
) -> Tuple[bool, str]:
    if not ctx.config.api_server:
        ctx.server_host = str("%s:%d" % (ctx.config.server_host, ctx.config.server_port))
        xlog.info("not api_server set, use server:%s specify in config.", ctx.server_host)
        return True, "success"

    if is_register:
        login_path = "/register"
        xlog.info("request_balance register:%s", account)
    else:
        login_path = "/login"

    if account is None:
        if not (ctx.config.login_account and ctx.config.login_password):
            xlog.debug("request_balance no account")
            return False, "no default account"

        account = ctx.config.login_account
        password = ctx.config.login_password

    app_name = get_app_name()
    req_info = {
        "account": account,
        "password": password,
        "protocol_version": "2",
        "promoter": promoter,
        "app_id": app_name,
        "client_version": ctx.xxnet_version,
        "sys_info": ctx.system,
    }

    try:
        ctx.center_login_process = True
        if ctx.tls_relay_front:
            ctx.tls_relay_front.set_x_tunnel_account(account, password)
        if ctx.seley_front:
            ctx.seley_front.set_x_tunnel_account(account, password)

        res, info = call_api(login_path, req_info)
        if not res:
            return False, info

        ctx.quota_list = info["quota_list"]
        ctx.quota = calculate_quota_left(ctx.quota_list)
        ctx.paypal_button_id = info["paypal_button_id"]
        ctx.plans = info["plans"]
        if ctx.quota <= 0:
            xlog.warn("no quota")

        if ctx.config.server_host:
            xlog.info("use server:%s specify in config.", ctx.config.server_host)
            ctx.server_host = str(ctx.config.server_host)
        elif update_server or not ctx.server_host:
            ctx.server_host = str(info["host"])
            ctx.server_port = info["port"]
            xlog.info("update xt_server %s:%d", ctx.server_host, ctx.server_port)

        ctx.selectable = info["selectable"]

        if ctx.config.update_cloudflare_domains:
            ctx.http_client.save_cloudflare_domain(info.get("cloudflare_domains"))

        ctx.promote_code = utils.to_str(info["promote_code"])
        ctx.promoter = info["promoter"]
        ctx.balance = info["balance"]
        ctx.openai_balance = info["openai_balance"]
        ctx.openai_proxies = info["openai_proxies"]
        ctx.tls_relays = info["tls_relays"]
        seleys = info.get("seleys", {})
        if ctx.tls_relay_front:
            ctx.tls_relay_front.set_ips(ctx.tls_relays["ips"])
        if ctx.seley_front:
            ctx.seley_front.set_hosts(seleys.get("hosts", {}))

        xlog.info("request_balance host:%s port:%d balance:%f quota:%f",
                  ctx.server_host, ctx.server_port, ctx.balance, ctx.quota)
        return True, "success"
    except Exception as e:
        ctx.last_api_error = "login center except: %r" % e
        xlog.exception("request_balance e:%r", e)
        return False, str(e)
    finally:
        ctx.center_login_process = False


async def async_request_balance(
    account: Optional[str] = None,
    password: Optional[str] = None,
    is_register: bool = False,
    update_server: bool = True,
    promoter: str = ""
) -> Tuple[bool, str]:
    if not ctx.config.api_server:
        ctx.server_host = str("%s:%d" % (ctx.config.server_host, ctx.config.server_port))
        xlog.info("not api_server set, use server:%s specify in config.", ctx.server_host)
        return True, "success"

    if is_register:
        login_path = "/register"
        xlog.info("async_request_balance register:%s", account)
    else:
        login_path = "/login"

    if account is None:
        if not (ctx.config.login_account and ctx.config.login_password):
            xlog.debug("async_request_balance no account")
            return False, "no default account"

        account = ctx.config.login_account
        password = ctx.config.login_password

    app_name = get_app_name()
    req_info = {
        "account": account,
        "password": password,
        "protocol_version": "2",
        "promoter": promoter,
        "app_id": app_name,
        "client_version": ctx.xxnet_version,
        "sys_info": ctx.system,
    }

    try:
        ctx.center_login_process = True
        if ctx.tls_relay_front:
            ctx.tls_relay_front.set_x_tunnel_account(account, password)
        if ctx.seley_front:
            ctx.seley_front.set_x_tunnel_account(account, password)

        res, info = await async_call_api(login_path, req_info)
        if not res:
            return False, info

        ctx.quota_list = info["quota_list"]
        ctx.quota = calculate_quota_left(ctx.quota_list)
        ctx.paypal_button_id = info["paypal_button_id"]
        ctx.plans = info["plans"]
        if ctx.quota <= 0:
            xlog.warn("no quota")

        if ctx.config.server_host:
            xlog.info("use server:%s specify in config.", ctx.config.server_host)
            ctx.server_host = str(ctx.config.server_host)
        elif update_server or not ctx.server_host:
            ctx.server_host = str(info["host"])
            ctx.server_port = info["port"]
            xlog.info("update xt_server %s:%d", ctx.server_host, ctx.server_port)

        ctx.selectable = info["selectable"]

        if ctx.config.update_cloudflare_domains:
            ctx.http_client.save_cloudflare_domain(info.get("cloudflare_domains"))

        ctx.promote_code = utils.to_str(info["promote_code"])
        ctx.promoter = info["promoter"]
        ctx.balance = info["balance"]
        ctx.openai_balance = info["openai_balance"]
        ctx.openai_proxies = info["openai_proxies"]
        ctx.tls_relays = info["tls_relays"]
        seleys = info.get("seleys", {})
        if ctx.tls_relay_front:
            ctx.tls_relay_front.set_ips(ctx.tls_relays["ips"])
        if ctx.seley_front:
            ctx.seley_front.set_hosts(seleys.get("hosts", {}))

        xlog.info("async_request_balance host:%s port:%d balance:%f quota:%f",
                  ctx.server_host, ctx.server_port, ctx.balance, ctx.quota)
        return True, "success"
    except Exception as e:
        ctx.last_api_error = "login center except: %r" % e
        xlog.exception("async_request_balance e:%r", e)
        return False, str(e)
    finally:
        ctx.center_login_process = False


def update_quota_loop() -> None:
    xlog.debug("update_quota_loop start.")

    start_time = time.time()
    last_quota = ctx.quota
    while ctx.running and time.time() - start_time < 10 * 60:
        if not ctx.config.login_account:
            xlog.info("update_quota_loop but logout.")
            return

        request_balance(
            ctx.config.login_account, ctx.config.login_password,
            is_register=False, update_server=False
        )

        if ctx.quota - last_quota > 1024 * 1024 * 1024:
            xlog.info("update_quota_loop quota updated")
            return

        time.sleep(60)

    xlog.warn("update_quota_loop timeout fail.")


async def async_update_quota_loop() -> None:
    xlog.debug("async_update_quota_loop start.")

    start_time = time.time()
    last_quota = ctx.quota
    while ctx.running and time.time() - start_time < 10 * 60:
        if not ctx.config.login_account:
            xlog.info("async_update_quota_loop but logout.")
            return

        await async_request_balance(
            ctx.config.login_account, ctx.config.login_password,
            is_register=False, update_server=False
        )

        if ctx.quota - last_quota > 1024 * 1024 * 1024:
            xlog.info("async_update_quota_loop quota updated")
            return

        await asyncio.sleep(60)

    xlog.warn("async_update_quota_loop timeout fail.")