#!/usr/bin/env python3
# coding:utf-8


if __name__ == "__main__":
    import os, sys
    current_path = os.path.dirname(os.path.abspath(__file__))
    python_path = os.path.abspath(os.path.join(current_path, os.pardir))
    noarch_lib = os.path.abspath(os.path.join(python_path, 'lib', 'noarch'))
    sys.path.append(noarch_lib)
    win32_lib = os.path.abspath(os.path.join(python_path, 'lib', 'win32'))
    sys.path.append(win32_lib)

import webbrowser
import os
import ctypes
import winreg as winreg
import win32_proxy_manager
import module_init
import update
from config import config, app_name

from xlog import getLogger
xlog = getLogger("launcher")
from systray import SysTrayIcon, win32_adapter

import locale
lang_code, code_page = locale.getdefaultlocale()


class Win_tray():
    def __init__(self):
        reg_path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        self.INTERNET_SETTINGS = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_ALL_ACCESS)

        icon_path = os.path.join(os.path.dirname(__file__), "web_ui", "img", app_name, "favicon.ico")
        self.systray = SysTrayIcon(icon_path, app_name, self.make_menu(), self.on_quit, left_click=self.on_show, right_click=self.on_right_click)

        proxy_setting = config.os_proxy_mode
        if proxy_setting == "x_tunnel" and config.enable_x_tunnel == 1:
            self.on_enable_x_tunnel()
        elif proxy_setting == "disable":
            pass
        else:
            xlog.warn("proxy_setting:%r", proxy_setting)

    def get_proxy_state(self):
        try:
            AutoConfigURL, reg_type = winreg.QueryValueEx(self.INTERNET_SETTINGS, 'AutoConfigURL')
            if AutoConfigURL:
                return "unknown"
        except OSError:
            pass

        try:
            ProxyEnable, reg_type = winreg.QueryValueEx(self.INTERNET_SETTINGS, 'ProxyEnable')
            if ProxyEnable:
                ProxyServer, reg_type = winreg.QueryValueEx(self.INTERNET_SETTINGS, 'ProxyServer')
                if ProxyServer == "127.0.0.1:1080":
                    return "x_tunnel"
                else:
                    return "unknown"
        except OSError:
            pass

        return "disable"

    def on_right_click(self):
        self.systray.update(menu=self.make_menu())
        self.systray._show_menu()

    def make_menu(self):
        proxy_stat = self.get_proxy_state()
        x_tunnel_checked = win32_adapter.fState.MFS_CHECKED if proxy_stat == "x_tunnel" else 0
        disable_checked = win32_adapter.fState.MFS_CHECKED if proxy_stat == "disable" else 0

        if lang_code == "zh_CN":
            menu_options = [("设置", None, self.on_show, 0)]
            if config.enable_x_tunnel == 1:
                menu_options.append(("全局通过X-Tunnel代理", None, self.on_enable_x_tunnel, x_tunnel_checked))

            menu_options += [
                ("取消全局代理", None, self.on_disable_proxy, disable_checked),
                ("重启各模块", None, self.on_restart_each_module, 0),
                ('退出', None, SysTrayIcon.QUIT, False)]
        else:
            menu_options = [("Config", None, self.on_show, 0)]
            if config.enable_x_tunnel == 1:
                menu_options.append(("Set Global X-Tunnel Proxy", None, self.on_enable_x_tunnel, x_tunnel_checked))

            menu_options += [
                ("Disable Global Proxy", None, self.on_disable_proxy, disable_checked),
                ("Reset Each module", None, self.on_restart_each_module, 0),
                ('Quit', None, SysTrayIcon.QUIT, False)]

        return tuple(menu_options)

    def on_show(self, widget=None, data=None):
        self.show_control_web()

    def on_restart_each_module(self, widget=None, data=None):
        module_init.stop_all()
        module_init.start_all_auto()

    def on_check_update(self, widget=None, data=None):
        update.check_update()

    def on_enable_x_tunnel(self, widget=None, data=None):
        win32_proxy_manager.set_proxy("127.0.0.1:1080")
        config.os_proxy_mode = "x_tunnel"
        config.save()

    def on_disable_proxy(self, widget=None, data=None):
        win32_proxy_manager.disable_proxy()
        config.os_proxy_mode = "disable"
        config.save()

    def show_control_web(self, widget=None, data=None):
        host_port = config.control_port
        url = "http://127.0.0.1:%s/" % host_port
        xlog.debug("Popup %s by tray", url)
        webbrowser.open(url)
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

    def on_quit(self, widget=None, data=None):
        if self.get_proxy_state() != "unknown":
            win32_proxy_manager.disable_proxy()

        module_init.stop_all()
        nid = win32_adapter.NotifyData(self.systray._hwnd, 0)
        win32_adapter.Shell_NotifyIcon(2, ctypes.byref(nid))
        os._exit(0)

    def serve_forever(self):
        self.systray._message_loop_func()

    def dialog_yes_no(self, msg="msg", title="Title", data=None, callback=None):
        res = ctypes.windll.user32.MessageBoxW(None, msg, title, 1)
        # Yes:1 No:2
        if callback:
            callback(data, res)
        return res


sys_tray = Win_tray()


def main():
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    sys_tray.serve_forever()


if __name__ == '__main__':
    main()
