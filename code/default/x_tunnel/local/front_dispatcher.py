from __future__ import annotations

import time
import threading
import os
import random
from threading import Lock
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Union

FRONT_FAIL_BASE_PENALTY: int = 1000
FRONT_PENALTY_DECAY_SECONDS: int = 30
FRONT_DISABLE_THRESHOLD: int = 10
FRONT_DISABLE_DURATION: int = 120

from .context import ctx
import utils
from log_buffer import getLogger
import env_info

current_path = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.abspath(os.path.join(current_path, os.pardir, os.pardir))
data_path = env_info.data_path
data_xtunnel_path = os.path.join(data_path, 'x_tunnel')

xlog = getLogger("x_tunnel", log_path=data_xtunnel_path, save_start_log=500, save_warning_log=True)

_FD_PROXY_ATTRS = frozenset({
    'all_fronts', 'light_fronts', 'session_fronts',
    'cloudflare_front', 'statistic_thread',
    '_initialized', '_statistic_running',
    '_front_fail_counts', '_front_last_fail_time',
})

_FD_NAME_MAP = {'_initialized': '_front_initialized'}


def __getattr__(name):
    if name in _FD_PROXY_ATTRS:
        return getattr(ctx, _FD_NAME_MAP.get(name, name))
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_init_lock: Lock = Lock()


def init() -> None:
    with _init_lock:
        if ctx._front_initialized:
            return

        ctx.all_fronts[:] = []
        ctx.session_fronts[:] = []
        ctx.light_fronts[:] = []
        ctx.cloudflare_front = None
        ctx.cloudfront_front = None
        ctx.seley_front = None
        ctx.tls_relay_front = None

        if ctx.config.enable_cloudflare:
            from .cloudflare_front.front import front as _cloudflare_front
            ctx.cloudflare_front = _cloudflare_front
            ctx.all_fronts.append(_cloudflare_front)
            ctx.session_fronts.append(_cloudflare_front)
            ctx.light_fronts.append(_cloudflare_front)

        if ctx.config.enable_cloudfront:
            from .cloudfront_front.front import front as cloudfront_front
            ctx.all_fronts.append(cloudfront_front)
            ctx.session_fronts.append(cloudfront_front)
            ctx.light_fronts.append(cloudfront_front)
            ctx.cloudfront_front = cloudfront_front

        if ctx.config.enable_seley:
            from .seley_front.front import front as seley_front
            ctx.all_fronts.append(seley_front)
            ctx.session_fronts.append(seley_front)
            ctx.light_fronts.append(seley_front)
            ctx.seley_front = seley_front

        if ctx.config.enable_tls_relay:
            from .tls_relay_front.front import front as tls_relay_front
            ctx.all_fronts.append(tls_relay_front)
            ctx.session_fronts.append(tls_relay_front)
            ctx.light_fronts.append(tls_relay_front)
            ctx.tls_relay_front = tls_relay_front

        if ctx.config.enable_direct:
            from . import direct_front
            ctx.all_fronts.append(direct_front)
            ctx.session_fronts.append(direct_front)
            ctx.light_fronts.append(direct_front)

        for front in ctx.all_fronts:
            front.start()

        ctx._statistic_running = True
        ctx.statistic_thread = threading.Thread(target=front_staticstic_thread, name="front_statistic_thread")
        ctx.statistic_thread.daemon = True
        ctx.statistic_thread.start()
        ctx._front_initialized = True


def save_cloudflare_domain(domains: List[str]) -> None:
    if not ctx.config.enable_cloudflare:
        xlog.warn("save_cloudflare_domain but cloudflare front not enabled")
        return

    for front in ctx.all_fronts:
        if front.name != "cloudflare_front":
            continue

        front.ip_manager.save_domains(domains)


def front_staticstic_thread() -> None:
    while ctx.running and ctx._statistic_running:
        for front in ctx.all_fronts:
            dispatcher = front.get_dispatcher()
            if not dispatcher:
                continue

            dispatcher.statistic()

        time.sleep(3)

get_front_lock = Lock()
_front_ready_cond = threading.Condition(get_front_lock)

def _is_front_disabled(front: Any) -> bool:
    disabled_time = ctx._front_disabled.get(front.name, 0)
    if disabled_time and time.time() - disabled_time < FRONT_DISABLE_DURATION:
        return True
    return False

def _get_front_penalty(front: Any) -> int:
    if _is_front_disabled(front):
        return 99999999
    
    fail_count = ctx._front_fail_counts.get(front.name, 0)
    success_count = ctx._front_success_counts.get(front.name, 0)
    
    if fail_count == 0:
        return 0
    
    last_fail = ctx._front_last_fail_time.get(front.name, 0)
    time_since_fail = time.time() - last_fail
    
    decay_factor = max(0, 1.0 - (time_since_fail / FRONT_PENALTY_DECAY_SECONDS))
    
    success_rate = 0.0
    total = fail_count + success_count
    if total > 0:
        success_rate = success_count / total
    
    penalty = fail_count * FRONT_FAIL_BASE_PENALTY * decay_factor
    
    if success_rate < 0.3 and fail_count > 5:
        penalty *= 3
    
    return int(penalty)

def _record_front_success(front: Any) -> None:
    ctx._front_fail_counts[front.name] = 0
    ctx._front_success_counts[front.name] = ctx._front_success_counts.get(front.name, 0) + 1
    if front.name in ctx._front_disabled:
        del ctx._front_disabled[front.name]
    notify_front_ready()

def _record_front_fail(front: Any) -> None:
    ctx._front_fail_counts[front.name] = ctx._front_fail_counts.get(front.name, 0) + 1
    ctx._front_last_fail_time[front.name] = time.time()
    
    fail_count = ctx._front_fail_counts[front.name]
    success_count = ctx._front_success_counts.get(front.name, 0)
    
    if fail_count >= FRONT_DISABLE_THRESHOLD:
        total = fail_count + success_count
        if total > 0 and (success_count / total) < 0.2:
            ctx._front_disabled[front.name] = time.time()
            xlog.warn("front %s disabled due to low success rate (%d/%d)", front.name, success_count, total)
    
    notify_front_ready()


def notify_front_ready() -> None:
    with _front_ready_cond:
        _front_ready_cond.notify_all()

def get_front(host: str, timeout: float) -> Optional[Any]:
    start_time = time.monotonic()
    if host in ["dns.xx-net.org", ctx.config.api_server]:
        fronts = ctx.light_fronts
    else:
        fronts = ctx.session_fronts

    with _front_ready_cond:
        while time.monotonic() - start_time < timeout:
            best_front = None
            best_score = 999999999
            available_fronts = 0
            for front in fronts:
                if _is_front_disabled(front):
                    continue
                
                if host == "dns.xx-net.org" and front == ctx.cloudflare_front and ctx.server_host:
                    host = ctx.server_host

                dispatcher = front.get_dispatcher(host)
                if not dispatcher:
                    continue

                available_fronts += 1
                score = dispatcher.get_score()
                if not score:
                    if front.config.show_state_debug:
                        xlog.warn("get_front get_score failed for %s ", front.name)
                    continue

                score += _get_front_penalty(front)

                if score < best_score:
                    best_score = score
                    best_front = front

            if best_front is not None:
                return best_front

            if available_fronts == 0:
                xlog.warn("all fronts disabled, resetting")
                ctx._front_disabled.clear()

            remaining = timeout - (time.monotonic() - start_time)
            if remaining <= 0:
                break
            _front_ready_cond.wait(min(0.1, remaining))

    ctx.stat["timeout_roundtrip"] += 5
    return None


def count_connection(host: str) -> int:
    fronts = ctx.session_fronts

    num = 0
    for front in fronts:
        dispatcher = front.get_dispatcher(host)
        if not dispatcher:
            continue

        num += len(dispatcher.workers)

        num += dispatcher.connection_manager.new_conn_pool.qsize()

    return num


def request(method: str, host: str, path: str = "/", headers: Dict[str, str] = {},
            data: Union[str, bytes] = "", timeout: float = 100) -> Tuple[Union[str, bytes], int, Any]:
    start_time = time.monotonic()

    content, status, response = "", 603, {}
    while time.monotonic() - start_time < timeout:
        remaining_timeout = timeout - (time.monotonic() - start_time)
        if remaining_timeout <= 0:
            break

        start_get_front = time.monotonic()
        front = get_front(host, remaining_timeout)
        if not front:
            xlog.warn("get_front fail")
            return "", 602, {}

        finished_get_front = time.monotonic()
        get_front_time = finished_get_front - start_get_front
        if get_front_time > 0.1:
            xlog.warn("get_front_time: %f for %s %s %s", get_front_time, method, host, path)

        if host == "dns.xx-net.org" and front == ctx.cloudflare_front and ctx.server_host:
            if ctx.server_host:
                host = ctx.server_host

        headers["X-Async"] = "1"
        if len(data) < 84:
            padding = utils.to_str(utils.generate_random_lowercase(random.randint(8, 64)))
            headers["Padding"] = padding

        request_timeout = timeout - (time.monotonic() - start_time)
        if request_timeout <= 0:
            break

        content, status, response = front.request(
            method, host=host, path=path, headers=dict(headers), data=data, timeout=request_timeout)

        if status not in [200, 521, 400, 404]:
            xlog.warn("front retry %s%s", host, path)
            _record_front_fail(front)
            remaining_timeout = timeout - (time.monotonic() - start_time)
            if remaining_timeout <= 0:
                break
            time.sleep(min(0.1, remaining_timeout))
            continue

        header_len = int(response.headers.get(b"Content-Length", 0))
        if header_len and len(content) != header_len:
            xlog.warn("response length incorrect, head len:%s, content len:%d retry it", header_len, len(content))
            _record_front_fail(front)
            remaining_timeout = timeout - (time.monotonic() - start_time)
            if remaining_timeout <= 0:
                break
            time.sleep(min(0.1, remaining_timeout))
            continue

        _record_front_success(front)
        return content, status, response

    return content, status, response


def set_session_host(host: str) -> None:
    for front in ctx.session_fronts:
        dispatcher = front.get_dispatcher(host)
        if not dispatcher:
            continue

        dispatcher.set_session_host(host)
    notify_front_ready()


def stop() -> None:
    ctx._statistic_running = False

    for front in ctx.all_fronts:
        front.stop()

    if ctx.statistic_thread and ctx.statistic_thread.is_alive() and ctx.statistic_thread is not threading.current_thread():
        ctx.statistic_thread.join(5)

    ctx.all_fronts = []
    ctx.light_fronts = []
    ctx.session_fronts = []
    ctx.cloudflare_front = None
    ctx.statistic_thread = None
    ctx.cloudfront_front = None
    ctx.seley_front = None
    ctx.tls_relay_front = None
    ctx._front_initialized = False
    ctx._front_fail_counts = {}
    ctx._front_last_fail_time = {}
    notify_front_ready()
