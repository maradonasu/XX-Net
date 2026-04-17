#!/usr/bin/env python3

import os
import subprocess
import locale
import json

from dataclasses import dataclass, field

import sys_platform
from http_client import request
import config_manager
from log_buffer import getLogger

xlog = getLogger("launcher")

current_path = os.path.dirname(os.path.abspath(__file__))
version_path = os.path.abspath(os.path.join(current_path, os.pardir))
root_path = os.path.abspath(os.path.join(version_path, os.pardir, os.pardir))

import env_info

data_path = env_info.data_path
config_path = os.path.join(data_path, 'launcher', 'config.json')


@dataclass
class LauncherConfig:
    control_ip: str = "127.0.0.1"
    control_port: int = 8085
    allowed_refers: list = field(default_factory=lambda: [""])

    language: str = ""
    allow_remote_connect: int = 0
    show_systray: int = 1
    show_android_notification: int = 1
    no_mess_system: int = 0
    auto_start: int = 0
    popup_webui: int = 1
    webui_auth: dict = field(default_factory=dict)

    show_detail: int = 0
    show_compat_suggest: int = 1
    proxy_by_app: int = 0
    enabled_app_list: list = field(default_factory=list)

    check_update: str = "notice-stable"
    keep_old_ver_num: int = 1
    postUpdateStat: str = "noChange"
    current_version: str = ""
    ignore_version: str = ""
    last_run_version: str = ""
    skip_stable_version: str = ""
    skip_test_version: str = ""

    last_path: str = ""
    update_uuid: str = ""

    clear_cache: int = 0
    del_win: int = 0
    del_mac: int = 0
    del_linux: int = 0
    del_xtunnel: int = 0

    all_modules: list = field(default_factory=lambda: ["launcher", "x_tunnel"])
    enable_launcher: int = 1
    enable_x_tunnel: int = 1

    os_proxy_mode: str = "x_tunnel"

    global_proxy_enable: int = 0
    global_proxy_type: str = "HTTP"
    global_proxy_host: str = ""
    global_proxy_port: int = 0
    global_proxy_username: str = ""
    global_proxy_password: str = ""


config = config_manager.TypedConfig(LauncherConfig, config_path)

app_name = "XX-Net"
valid_language = ['en_US', 'fa_IR', 'zh_CN', 'ru_RU']
try:
    fp = os.path.join(root_path, "code", "app_info.json")
    with open(fp, "r") as fd:
        app_info = json.load(fd)
        app_name = app_info["app_name"]
except Exception as e:
    print("load app_info except:", e)


def _get_os_language():

    if sys_platform.platform == "mac":
        try:
            lang_code = subprocess.check_output(["/usr/bin/defaults", 'read', 'NSGlobalDomain', 'AppleLanguages'])
            if b'zh' in lang_code:
                return 'zh_CN'
            elif b'en' in lang_code:
                return 'en_US'
            elif b'fa' in lang_code:
                return 'fa_IR'
            elif b'ru' in lang_code:
                return 'ru_RU'

        except (subprocess.SubprocessError, OSError):
            pass
    elif sys_platform.platform == "android":
        try:
            res = request("GET", "http://localhost:8084/env/")
            dat = json.loads(res.text)
            lang_code = dat["lang_code"]
            xlog.debug("lang_code:%s", lang_code)
            if 'zh' in lang_code:
                return 'zh_CN'
            elif 'en' in lang_code:
                return 'en_US'
            elif 'fa' in lang_code:
                return 'fa_IR'
            elif 'ru' in lang_code:
                return 'ru_RU'
            else:
                return None
        except Exception as e:
            xlog.warn("get lang except:%r", e)
            return "zh_CN"
    elif sys_platform.platform == "ios":
        lang_code = os.environ["IOS_LANG"]
        if 'zh' in lang_code:
            return 'zh_CN'
        elif 'en' in lang_code:
            return 'en_US'
        elif 'fa' in lang_code:
            return 'fa_IR'
        elif 'ru' in lang_code:
            return 'ru_RU'
        else:
            return None
    else:
        try:
            lang_code, code_page = locale.getdefaultlocale()
            return lang_code
        except Exception:
            pass


def get_language():
    if config.language:
        lang = config.language
    else:
        lang = _get_os_language()

    if lang not in valid_language:
        lang = 'en_US'

    return lang
