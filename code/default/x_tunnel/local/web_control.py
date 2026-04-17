#!/usr/bin/env python3
# coding:utf-8


from urllib.parse import urlparse, parse_qs

import os
import time
import hashlib
import threading
import json
import base64
import inspect

import utils
from log_buffer import getLogger
xlog = getLogger("x_tunnel")

import http_server
import async_loop
from .context import ctx
from . import api_client
from .config import XTunnelConfig

current_path = os.path.dirname(os.path.abspath(__file__))
default_path = os.path.abspath(os.path.join(current_path, os.pardir, os.pardir))
root_path = os.path.abspath(os.path.join(default_path, os.pardir, os.pardir))
web_ui_path = os.path.join(current_path, os.path.pardir, "web_ui")

import env_info
data_path = os.path.join(env_info.data_path, 'x_tunnel')
_task_lock = threading.Lock()
_background_tasks = {}


def _get_tls_relay_web():
    from .tls_relay_front import web_control as tls_relay_web
    return tls_relay_web


def run_session_action(session, action, *args, **kwargs):
    if not session:
        return None

    method = getattr(session, action)
    result = method(*args, **kwargs)
    if inspect.iscoroutine(result):
        return async_loop.run_async(result)
    return result


def _start_background_task(name, target, args=()):
    with _task_lock:
        thread = _background_tasks.get(name)
        if thread and thread.is_alive():
            return False

        def runner():
            try:
                target(*args)
            finally:
                with _task_lock:
                    current = _background_tasks.get(name)
                    if current is threading.current_thread():
                        _background_tasks.pop(name, None)

        thread = threading.Thread(target=runner, name=name)
        thread.daemon = True
        _background_tasks[name] = thread
        thread.start()
        return True


def check_email(email):
    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return False
    else:
        return True


def get_lang():
    app_info_file = os.path.join(env_info.data_path, "launcher", "config.json")
    try:
        with open(app_info_file, "r") as fd:
            dat = json.load(fd)
        return dat.get("language", "en")
    except Exception as e:
        xlog.exception("get version fail:%r", e)
    return "en"


class ControlHandler(http_server.HttpServerHandler):
    def __init__(self, client_address, headers, command, path, rfile, wfile):
        self.client_address = client_address
        self.headers = headers
        self.command = command
        self.path = path
        self.rfile = rfile
        self.wfile = wfile
        self.res_headers = {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/log":
            return self.req_log_handler()
        elif path == "/debug":
            data = ctx.session.status()
            return self.send_response('text/plain', data)
        elif path == "/info":
            return self.req_info_handler()
        elif path == "/config":
            return self.req_config_handler()
        elif path == "/get_history":
            return self.req_get_history_handler()
        elif path == "/status":
            return self.req_status()
        elif path.startswith("/cloudflare_front/"):
            path = self.path[17:]
            from .cloudflare_front import web_control as cloudflare_web
            controler = cloudflare_web.ControlHandler(self.client_address,
                             self.headers,
                             self.command, path,
                             self.rfile, self.wfile)
            controler.do_GET()
        elif path.startswith("/cloudfront_front/"):
            if not ctx.config.enable_cloudfront:
                return self.send_not_found()

            path = self.path[17:]
            from .cloudfront_front import web_control as cloudfront_web
            controler = cloudfront_web.ControlHandler(self.client_address,
                             self.headers,
                             self.command, path,
                             self.rfile, self.wfile)
            controler.do_GET()
        elif path.startswith("/seley_front/"):
            path = self.path[12:]
            from .seley_front import web_control as seley_web
            controler = seley_web.ControlHandler(self.client_address,
                             self.headers,
                             self.command, path,
                             self.rfile, self.wfile)
            controler.do_GET()
        elif path.startswith("/tls_relay_front/"):
            path = self.path[16:]
            tls_relay_web = _get_tls_relay_web()
            controler = tls_relay_web.ControlHandler(self.client_address,
                             self.headers,
                             self.command, path,
                             self.rfile, self.wfile)
            controler.do_GET()
        else:
            xlog.warn('Control Req %s %s %s ', self.address_string(), self.command, self.path)

    def do_POST(self):
        xlog.debug('x-tunnel web_control %s %s %s ', self.address_string(), self.command, self.path)

        path = urlparse(self.path).path
        if path == '/token_login':
            return self.req_token_login_handler()
        elif path == '/login':
            return self.req_login_handler()
        elif path == "/logout":
            return self.req_logout_handler()
        elif path == "/register":
            return self.req_login_handler()
        elif path == "/config":
            return self.req_config_handler()
        elif path == "/order":
            return self.req_order_handler()
        elif path == "/transfer":
            return self.req_transfer_handler()
        elif path == "/reset_password":
            return self.req_reset_password()
        elif path.startswith("/cloudflare_front/"):
            path = path[17:]
            from .cloudflare_front import web_control as cloudflare_web
            controler = cloudflare_web.ControlHandler(self.client_address,
                                                      self.headers,
                                                      self.command, path,
                                                      self.rfile, self.wfile)
            controler.do_POST()
        elif path.startswith("/cloudfront_front/"):
            path = path[17:]
            from .cloudfront_front import web_control as cloudfront_web
            controler = cloudfront_web.ControlHandler(self.client_address,
                                                      self.headers,
                                                      self.command, path,
                                                      self.rfile, self.wfile)
            controler.do_POST()
        elif path.startswith("/seley_front/"):
            path = path[13:]

            from .seley_front import web_control as seley_web
            controler = seley_web.ControlHandler(self.client_address,
                                                      self.headers,
                                                      self.command, path,
                                                      self.rfile, self.wfile)
            controler.do_POST()
        elif path.startswith("/tls_relay_front/"):
            path = path[16:]
            tls_relay_web = _get_tls_relay_web()
            controler = tls_relay_web.ControlHandler(self.client_address,
                                                      self.headers,
                                                      self.command, path,
                                                      self.rfile, self.wfile)
            controler.do_POST()
        else:
            xlog.info('%s "%s %s HTTP/1.1" 404 -', self.address_string(), self.command, self.path)
            return self.send_not_found()

    def req_log_handler(self):
        req = urlparse(self.path).query
        reqs = self.unpack_reqs(parse_qs(req, keep_blank_values=True))
        data = ''

        if reqs["cmd"]:
            cmd = reqs["cmd"]
        else:
            cmd = "get_last"

        if cmd == "get_last":
            max_line = int(reqs["max_line"])
            data = xlog.get_last_lines(max_line)
        elif cmd == "get_new":
            last_no = int(reqs["last_no"])
            data = xlog.get_new_lines(last_no)
        else:
            xlog.error('xtunnel log cmd:%s', cmd)

        mimetype = 'text/plain'
        self.send_response(mimetype, data)

    def req_info_handler(self):
        if len(ctx.config.login_account) == 0 or len(ctx.config.login_password) == 0:
            return self.response_json({
                "res": "logout"
            })

        if ctx.center_login_process:
            return self.response_json({
                "res": "login_process"
            })

        req = urlparse(self.path).query
        reqs = parse_qs(req, keep_blank_values=True)

        force = False
        if 'force' in reqs:
            xlog.debug("req_info in force")
            force = 1

        time_now = time.time()
        if force or time_now - ctx.last_refresh_time > 3600 or \
                (ctx.last_api_error.startswith("status:") and (time_now - ctx.last_refresh_time > 30)):
            xlog.debug("x_tunnel force update info")
            ctx.last_refresh_time = time_now

            _start_background_task("info__request_balance", api_client.request_balance,
                                   args=(None, None, False, False))

            return self.response_json({
                "res": "login_process"
            })

        if len(ctx.last_api_error) and ctx.last_api_error != 'balance not enough':
            res_arr = {
                "res": "fail",
                "login_account": "%s" % (ctx.config.login_account),
                "reason": ctx.last_api_error
            }
        else:
            res_arr = {
                "res": "success",
                "login_account": "%s" % (ctx.config.login_account),
                "promote_code": ctx.promote_code,
                "promoter": ctx.promoter,
                "paypal_button_id": ctx.paypal_button_id,
                "plans": ctx.plans,
                "balance": "%f" % (ctx.balance),
                "openai_balance": float(ctx.openai_balance),
                "quota": "%d" % (ctx.quota),
                "quota_list": ctx.quota_list,
                "traffic": ctx.session.traffic_upload + ctx.session.traffic_download,
                "last_fail": ctx.last_api_error
            }
        self.response_json(res_arr)

    def req_token_login_handler(self):
        login_token = str(self.postvars['login_token'])
        try:
            login_str = base64.b64decode(login_token)
            data = json.loads(utils.to_str(login_str))
            username = data["login_account"]
            password_hash = data["login_password"]
            cloudflare_domains = data.get("cloudflare_domains")
            tls_relay = data["tls_relay"]
            seleys = data.get("seleys", {})
        except Exception as e:
            xlog.warn("token_login except:%r", e)
            return self.response_json({
                "res": "fail",
                "reason": "token invalid"
            })

        pa = check_email(username)
        if not pa:
            xlog.warn("login with invalid email: %s", username)
            return self.response_json({
                "res": "fail",
                "reason": "Invalid email."
            })
        elif len(password_hash) < 64:
            return self.response_json({
                "res": "fail",
                "reason": "Password format fail"
            })

        ctx.config.api_server = ctx.config.api_server or XTunnelConfig.api_server
        if ctx.config.update_cloudflare_domains and cloudflare_domains:
            ctx.http_client.save_cloudflare_domain(cloudflare_domains)
        if ctx.tls_relay_front and tls_relay.get("ips"):
            ctx.tls_relay_front.set_ips(tls_relay["ips"])
        if ctx.seley_front:
            ctx.seley_front.set_hosts(seleys.get("hosts", {}))

        res, reason = api_client.request_balance(username, password_hash, False,
                                                    update_server=True, promoter="")
        if res:
            ctx.config.login_account  = username
            ctx.config.login_password = password_hash
            ctx.config.save()
            res_arr = {
                "res": "success",
                "balance": float(ctx.balance),
                "openai_balance": float(ctx.openai_balance)
            }
            ctx.last_refresh_time = time.time()
            run_session_action(ctx.session, "start")
        else:
            res_arr = {
                "res": "fail",
                "reason": reason
            }

        return self.response_json(res_arr)

    def req_login_handler(self):
        username    = str(self.postvars['username'])
        #username = utils.get_printable(username)
        password    = str(self.postvars['password'])
        promoter = self.postvars.get("promoter", [""])
        is_register = int(self.postvars['is_register'])

        pa = check_email(username)
        if not pa:
            xlog.warn("login with invalid email: %s", username)
            return self.response_json({
                "res": "fail",
                "reason": "Invalid email."
            })
        elif len(password) < 6:
            return self.response_json({
                "res": "fail",
                "reason": "Password needs at least 6 charactors."
            })

        if password == "_HiddenPassword":
            if username == ctx.config.login_account and len(ctx.config.login_password):
                password_hash = ctx.config.login_password
            else:

                res_arr = {
                    "res": "fail",
                    "reason": "account not exist"
                }
                return self.response_json(res_arr)
        else:
            password_hash = str(hashlib.sha256(utils.to_bytes(password)).hexdigest())

        res, reason = api_client.request_balance(username, password_hash, is_register,
                                                    update_server=True, promoter=promoter)
        if res:
            ctx.config.login_account  = username
            ctx.config.login_password = password_hash
            ctx.config.save()
            res_arr = {
                "res": "success",
                "balance": float(ctx.balance),
                "openai_balance": float(ctx.openai_balance)
            }
            ctx.last_refresh_time = time.time()
            run_session_action(ctx.session, "start")
        else:
            res_arr = {
                "res": "fail",
                "reason": reason
            }

        return self.response_json(res_arr)

    def req_reset_password(self):
        app_name = api_client.get_app_name()
        account = self.postvars.get('username', [""])
        stage = self.postvars.get('stage', [""])
        code = self.postvars.get('code', [""])
        xlog.info("reset password, stage:%s", stage)

        if stage == "request_reset_password":
            res, info = api_client.call_api("/request_reset_password", {
                "account": account,
                "app_id": app_name,
                "lang": get_lang(),
            })
            if not res:
                xlog.warn("request reset password fail:%s", info)
                _start_background_task("update_quota_loop", api_client.update_quota_loop)
                return self.response_json({"res": "fail", "reason": info})

            self.response_json(info)

        elif stage == "reset_password_check":
            res, info = api_client.call_api("/reset_password_check", {
                "account": account,
                "code": code,
                "app_id": app_name,
                "lang": get_lang(),
            })
            if not res:
                xlog.warn("reset password check fail:%s", info)
                _start_background_task("update_quota_loop", api_client.update_quota_loop)
                return self.response_json({"res": "fail", "reason": info})

            self.response_json(info)

        elif stage == "change_password":
            password = self.postvars.get('password', [""])
            password_hash = str(hashlib.sha256(utils.to_bytes(password)).hexdigest())
            res, info = api_client.call_api("/change_password", {
                "account": account,
                "code": code,
                "password": password_hash,
                "app_id": app_name,
                "lang": get_lang(),
            })
            if not res:
                xlog.warn("change password fail:%s", info)
                _start_background_task("update_quota_loop", api_client.update_quota_loop)
                return self.response_json({"res": "fail", "reason": info})

            self.response_json(info)
        else:
            self.response_json({"res": "fail", "reason": "wrong stage"})

    def req_logout_handler(self):
        ctx.config.login_account = ""
        ctx.config.login_password = ""
        ctx.config.save()

        if ctx.session:
            run_session_action(ctx.session, "stop")

        return self.response_json({"res": "success"})

    def req_config_handler(self):
        req = urlparse(self.path).query
        reqs = parse_qs(req, keep_blank_values=True)

        def is_server_available(server):
            if ctx.selectable and server == '':
                return True # "auto"
            else:
                for choice in ctx.selectable:
                    if choice[0] == server:
                        return True # "selectable"
                return False # "unselectable"

        if reqs['cmd'] == ['get']:
            ctx.config.load()
            server = {
                'selectable': ctx.selectable,
                'selected': 'auto' if ctx.config.server_host == '' else ctx.config.server_host,  # "auto" as default
                'available': is_server_available(ctx.config.server_host)
            }
            res = {
                'server': server,
                'promoter': ctx.promoter
            }
        elif reqs['cmd'] == ['set']:
            if 'server' in self.postvars:
                server = str(self.postvars['server'])
                server = '' if server == 'auto' else server

                if is_server_available(server):
                    if server != ctx.config.server_host:
                        xlog.info("change server to %s", server)
                        ctx.server_host = ctx.config.server_host = server
                        ctx.server_port = ctx.config.server_port = 443
                        ctx.config.save()

                        _start_background_task("session_reset", run_session_action, args=(ctx.session, "reset"))

                    res = {"res": "success"}
                else:
                    res = {
                        "res": "fail",
                        "reason": "server not available"
                    }
            else:
                res = {"res": "fail"}

        return self.response_json(res)

    def req_order_handler(self):
        product = self.postvars['product']
        if product != 'x_tunnel':
            xlog.warn("x_tunnel order product %s not support", product)
            return self.response_json({
                "res": "fail",
                "reason": "product %s not support" % product
            })

        plan = self.postvars['plan']
        if plan not in ctx.plans:
            xlog.warn("x_tunnel order plan %s not support", plan)
            return self.response_json({
                "res": "fail",
                "reason": "plan %s not support" % plan
            })

        res, info = api_client.call_api("/order", {
            "account": ctx.config.login_account,
            "password": ctx.config.login_password,
            "product": "x_tunnel",
            "plan": plan
        })
        if not res:
            xlog.warn("order fail:%s", info)
            _start_background_task("update_quota_loop", api_client.update_quota_loop)
            return self.response_json({"res": "fail", "reason": info})

        self.response_json({"res": "success"})

    def req_transfer_handler(self):
        to_account = self.postvars['to_account']
        amount = float(self.postvars['amount'])
        transfer_type = self.postvars['transfer_type']
        if transfer_type == 'balance':
            if amount > ctx.balance:
                reason = "balance not enough"
                xlog.warn("transfer fail:%s", reason)
                return self.response_json({"res": "fail", "reason": reason})
            end_time = 0
        elif transfer_type == "quota":
            end_time = int(self.postvars['end_time'])
        else:
            reason = "transfer type not support:%s" % transfer_type
            xlog.warn("transfer fail:%s", reason)
            return self.response_json({"res": "fail", "reason": reason})

        req_info = {
            "account": ctx.config.login_account,
            "password": ctx.config.login_password,
            "transfer_type": transfer_type,
            "end_time": end_time,
            "to_account": to_account,
            "amount": amount
        }

        res, info = api_client.call_api("/transfer", req_info)
        if not res:
            xlog.warn("transfer fail:%s", info)
            return self.response_json({
                "res": "fail",
                "reason": info
            })

        self.response_json({"res": "success"})

    def req_get_history_handler(self):
        req = urlparse(self.path).query
        reqs = parse_qs(req, keep_blank_values=True)

        req_info = {
            "account": ctx.config.login_account,
            "password": ctx.config.login_password,
            "start": int(reqs['start'][0]),
            "end": int(reqs['end'][0]),
            "limit": int(reqs['limit'][0])
        }

        res, info = api_client.call_api("/get_history", req_info)
        if not res:
            xlog.warn("get history fail:%s", info)
            return self.response_json({
                "res": "fail",
                "reason": info
            })
        self.response_json({
            "res": "success",
            "history": info["history"]
        })

    def req_status(self):
        res = ctx.session.get_stat()
        res["bind_port"] = ctx.bind_port

        self.response_json({
            "res": "success",
            "status": res
        })
