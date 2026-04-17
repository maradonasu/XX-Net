#!/usr/bin/env python3
# coding:utf-8

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import xstruct as struct
from typing import Any, Dict, List, Optional, Tuple, Union

from log_buffer import getLogger, keep_log
xlog = getLogger("x_tunnel")

import utils
import encrypt
from . import global_var as g
from .async_base_container import (
    AsyncWaitQueue, AsyncSendBuffer, AsyncConnectionPipe,
    AsyncConn, AsyncBlockReceivePool
)
from . import base_container
from . import proxy_session


def encrypt_data(data: Union[bytes, bytearray]) -> bytes:
    if g.config and g.config.encrypt_data:
        return encrypt.Encryptor(g.config.encrypt_password, g.config.encrypt_method).encrypt(data)
    return data


def decrypt_data(data: Union[bytes, memoryview]) -> bytes:
    if g.config and getattr(g.config, 'encrypt_data', None):
        if isinstance(data, memoryview):
            data = data.tobytes()
        return encrypt.Encryptor(g.config.encrypt_password, g.config.encrypt_method).decrypt(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    return data


def traffic_readable(num: float, units: Tuple[str, str, str, str] = ('B', 'KB', 'MB', 'GB')) -> str:
    for unit in units:
        if num >= 1024:
            num /= 1024.0
        else:
            break
    return '{:.1f} {}'.format(num, unit)


class AsyncReceiveProcess:
    def __init__(self, handler: callable, logger: Any) -> None:
        self._handler = handler
        self.xlog = logger
        self._lock: asyncio.Lock = asyncio.Lock()
        
        self.next_sn: int = 1
        self.block_list: List[int] = []
        self.timeout_list: Dict[int, dict] = {}
    
    async def put(self, sn: int, data: bytes) -> None:
        async with self._lock:
            if sn in self.timeout_list:
                del self.timeout_list[sn]
            
            if sn < self.next_sn:
                return
            
            if sn > self.next_sn:
                if sn in self.block_list:
                    return
                self.block_list.append(sn)
                try:
                    await self._handler(data)
                except Exception as e:
                    self.xlog.warn("receive handler error: %r", e)
                return
            
            try:
                await self._handler(data)
            except Exception as e:
                self.xlog.warn("receive handler error: %r", e)
            self.next_sn += 1
            
            while self.next_sn in self.block_list:
                self.block_list.remove(self.next_sn)
                self.next_sn += 1
    
    def is_received(self, sn: int) -> bool:
        return sn < self.next_sn or sn in self.block_list
    
    async def mark_sn_timeout(self, sn: int, t: float, server_time: float) -> None:
        async with self._lock:
            if sn not in self.timeout_list:
                self.xlog.warn("mark_sn_timeout sn:%d t:%f", sn, server_time - t)
                self.timeout_list[sn] = {"server_send_time": t}
            elif t > self.timeout_list[sn]["server_send_time"]:
                self.timeout_list[sn]["server_send_time"] = t
    
    async def get_timeout_list(self, server_time: float, timeout: float) -> List[int]:
        result = []
        async with self._lock:
            for sn, info in list(self.timeout_list.items()):
                if server_time - info["server_send_time"] < timeout:
                    continue
                if server_time - info.get("retry_time", server_time) < timeout:
                    continue
                self.xlog.warn("get_timeout_list sn:%d sent:%f retry:%f",
                               sn, server_time - info["server_send_time"],
                               server_time - info.get("retry_time", server_time))
                info["retry_time"] = server_time
                result.append(sn)
        return result
    
    async def reset(self) -> None:
        async with self._lock:
            self.next_sn = 1
            self.block_list = []
            self.timeout_list = {}
    
    def status(self) -> str:
        out = "AsyncReceiveProcess:\n"
        out += f" next_sn: {self.next_sn}\n"
        out += f" block_list: {self.block_list}\n"
        return out


class AsyncProxySession:
    def __init__(self) -> None:
        self.config = g.config
        
        max_payload = 65536
        windows_size = 65536
        windows_ack = 40
        send_delay = 100
        ack_delay = 100
        resend_timeout = 10000
        concurent_thread_num = 4
        min_on_road = 2
        roundtrip_timeout = 30
        network_timeout = 30
        send_timeout_retry = 60
        server_time_max_deviation = 5
        server_download_timeout_retry = 300
        
        if self.config:
            if hasattr(self.config, 'max_payload'):
                max_payload = self.config.max_payload
            if hasattr(self.config, 'windows_size'):
                windows_size = self.config.windows_size
            if hasattr(self.config, 'windows_ack'):
                windows_ack = self.config.windows_ack
            if hasattr(self.config, 'send_delay'):
                send_delay = self.config.send_delay
            if hasattr(self.config, 'ack_delay'):
                ack_delay = self.config.ack_delay
            if hasattr(self.config, 'resend_timeout'):
                resend_timeout = self.config.resend_timeout
            if hasattr(self.config, 'concurent_thread_num'):
                concurent_thread_num = self.config.concurent_thread_num
            if hasattr(self.config, 'min_on_road'):
                min_on_road = self.config.min_on_road
            if hasattr(self.config, 'roundtrip_timeout'):
                roundtrip_timeout = self.config.roundtrip_timeout
            if hasattr(self.config, 'network_timeout'):
                network_timeout = self.config.network_timeout
            if hasattr(self.config, 'send_timeout_retry'):
                send_timeout_retry = self.config.send_timeout_retry
            if hasattr(self.config, 'server_time_max_deviation'):
                server_time_max_deviation = self.config.server_time_max_deviation
            if hasattr(self.config, 'server_download_timeout_retry'):
                server_download_timeout_retry = self.config.server_download_timeout_retry
        
        self.max_payload = max_payload
        self.windows_size = windows_size
        self.windows_ack = windows_ack
        self.send_delay = send_delay / 1000.0
        self.ack_delay = ack_delay / 1000.0
        self.resend_timeout = resend_timeout / 1000.0
        self.concurent_thread_num = concurent_thread_num
        self.min_on_road = min_on_road
        self.roundtrip_timeout = roundtrip_timeout
        self.network_timeout = network_timeout
        self.send_timeout_retry = send_timeout_retry
        self.server_time_max_deviation = server_time_max_deviation
        self.server_download_timeout_retry = server_download_timeout_retry
        
        self.wait_queue = AsyncWaitQueue()
        self.send_buffer = AsyncSendBuffer(max_payload=max_payload)
        self.receive_process = AsyncReceiveProcess(self.download_data_processor, xlog)
        self.connection_pipe = AsyncConnectionPipe(self, xlog)
        self.lock: asyncio.Lock = asyncio.Lock()
        self.get_data_lock: asyncio.Lock = asyncio.Lock()
        
        self.running: bool = False
        self._tasks: List[asyncio.Task] = []
        self.session_id: bytes = utils.to_bytes(utils.generate_random_lowercase(8))
        self.conn_list: Dict[int, AsyncConn] = {}
        self.last_conn_id: int = 0
        self.last_transfer_no: int = 0
        
        self.wait_ack_send_list: Dict[int, Union[Tuple[bytes, float], str]] = {}
        self.ack_send_continue_sn: int = 0
        self.transfer_list: Dict[int, Dict[str, Any]] = {}
        
        self.traffic_upload: int = 0
        self.traffic_download: int = 0
        self.last_traffic_upload: int = 0
        self.last_traffic_download: int = 0
        self.last_traffic_reset_time: float = time.time()
        self.upload_speed: float = 0.0
        self.download_speed: float = 0.0
        
        self.last_send_time: float = 0
        self.last_receive_time: float = 0
        self.server_time_offset: float = 0
        self.server_time_deviation: float = 9999
        self.target_on_roads: int = 0
        self.on_road_num: int = 0
        self.oldest_received_time: float = 0
        
        self.last_state = {"timeout": 0}
    
    async def start(self) -> bool:
        async with self.lock:
            if self.running:
                xlog.warn("AsyncProxySession try to start but already running")
                return True
            
            self.session_id = utils.to_bytes(utils.generate_random_lowercase(8))
            self.last_conn_id = 0
            self.last_transfer_no = 0
            self.conn_list = {}
            self.transfer_list = {}
            self.wait_ack_send_list = {}
            self.ack_send_continue_sn = 0
            self.last_send_time = time.time()
            self.last_receive_time = 0
            self.oldest_received_time = 0
            self.target_on_roads = 0
            self.on_road_num = 0
            self.server_time_offset = 0
            self.server_time_deviation = 9999
            
            self.traffic_upload = 0
            self.traffic_download = 0
            self.last_traffic_upload = 0
            self.last_traffic_download = 0
            self.last_traffic_reset_time = time.time()
            
            if not await self.login_session():
                xlog.warn("AsyncProxySession login failed")
                return False
            
            self.running = True
            
            self.wait_queue.reset()
            await self.send_buffer.reset()
            await self.receive_process.reset()
            
            for i in range(self.concurent_thread_num):
                task = asyncio.create_task(self.round_trip_worker(i), name=f"roundtrip_{i}")
                self._tasks.append(task)
            
            task = asyncio.create_task(self.timeout_checker(), name="timeout_checker")
            self._tasks.append(task)
            
            await self.connection_pipe.start()
            xlog.info("AsyncProxySession started")
            return True
    
    async def stop(self) -> None:
        if not self.running:
            return
        
        self.running = False
        self.wait_queue.stop()
        
        for task in self._tasks:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        self._tasks.clear()
        
        await self.close_all_connections()
        await self.send_buffer.reset()
        await self.receive_process.reset()
        await self.connection_pipe.stop()
        
        xlog.info("AsyncProxySession stopped")
    
    async def reset(self) -> bool:
        xlog.debug("AsyncProxySession reset")
        await self.stop()
        return await self.start()
    
    def is_idle(self) -> bool:
        return time.time() - self.last_send_time > 60
    
    def traffic_speed_calculation(self) -> None:
        now = time.time()
        time_go = now - self.last_traffic_reset_time
        if time_go > 0.5:
            self.upload_speed = (self.traffic_upload - self.last_traffic_upload) / time_go
            self.download_speed = (self.traffic_download - self.last_traffic_download) / time_go
            
            self.last_traffic_reset_time = now
            self.last_traffic_upload = self.traffic_upload
            self.last_traffic_download = self.traffic_download
    
    def trigger_more(self) -> None:
        running_num = self.concurent_thread_num - self.wait_queue.waiters
        action_num = self.target_on_roads - running_num
        if action_num <= 0:
            return
        for _ in range(action_num):
            self.wait_queue.notify()
    
    async def round_trip_worker(self, work_id: int) -> None:
        xlog.debug("round_trip_worker %d started", work_id)
        try:
            while self.running:
                result = await self.roundtrip_task(work_id)
                if result is None:
                    await self.wait_queue.wait(timeout=1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            xlog.exception("round_trip_worker %d error: %r", work_id, e)
        xlog.info("round_trip_worker %d exit", work_id)
    
    async def roundtrip_task(self, work_id: int) -> Optional[bool]:
        async with self.get_data_lock:
            data_info = await self.get_upload_data(work_id)
            if not data_info:
                return None
            
            request_session_id = data_info.get("request_session_id", self.session_id)
            if request_session_id != self.session_id:
                return None
            
            transfer_no = data_info["transfer_no"]
            start_time = data_info["start_time"]
            send_data = data_info["send_data"]
            send_ack = data_info["send_ack"]
            download_timeout = data_info["download_timeout"]
            
            send_data_len = len(send_data)
            send_ack_len = len(send_ack)
            download_timeout_len = len(download_timeout)
            
            server_timeout = 0
            if len(self.send_buffer) > self.max_payload or \
               self.concurent_thread_num - self.on_road_num < self.min_on_road or \
               self.server_time_deviation > self.server_time_max_deviation or \
               data_info["stat"] == "retry":
                server_timeout = 0
            else:
                server_timeout = self.roundtrip_timeout
            
            async with self.lock:
                if transfer_no not in self.transfer_list:
                    xlog.warn("roundtrip transfer_no not found:%d", transfer_no)
                    return None
                
                self.on_road_num += 1
                self.transfer_list[transfer_no]["server_timeout"] = server_timeout
        
        magic = b"P"
        pack_type = 2
        protocol_version = g.protocol_version if hasattr(g, 'protocol_version') else 1
        
        upload_data_head = struct.pack("<cBB8sIBIHH", magic, protocol_version, pack_type,
                                       self.session_id, transfer_no,
                                       server_timeout, send_data_len, send_ack_len, download_timeout_len)
        upload_post_buf = base_container.WriteBuffer(upload_data_head)
        upload_post_buf.append(send_data)
        upload_post_buf.append(send_ack)
        upload_post_buf.append(download_timeout)
        upload_post_data = upload_post_buf.to_bytes()
        upload_post_data = encrypt_data(upload_post_data)
        self.last_send_time = time.time()
        
        try:
            request_timeout = server_timeout + self.network_timeout
            if send_data_len > 0:
                request_timeout = min(request_timeout, self.send_timeout_retry + self.network_timeout)
            
            upload_post_data2 = bytearray(upload_post_data)
            loop = asyncio.get_event_loop()
            content, status, response = await loop.run_in_executor(
                None,
                lambda: g.http_client.request(
                    method="POST",
                    host=g.server_host,
                    path="/data?tid=%d" % transfer_no,
                    data=upload_post_data2,
                    headers={"Content-Length": str(len(upload_post_data2))},
                    timeout=request_timeout
                )
            )
            
            traffic = len(upload_post_data2) + len(content) + 645
            self.traffic_upload += len(upload_post_data2) + 645
            self.traffic_download += len(content)
            if hasattr(g, 'quota'):
                g.quota -= traffic
                if g.quota < 0:
                    g.quota = 0
            
        except Exception as e:
            if self.running:
                xlog.exception("request except:%r ", e)
            async with self.lock:
                if transfer_no in self.transfer_list:
                    self.transfer_list[transfer_no]["stat"] = "timeout"
            await asyncio.sleep(1)
            return False
        finally:
            async with self.lock:
                self.on_road_num -= 1
        
        if hasattr(g, 'stat'):
            g.stat["roundtrip_num"] += 1
        time_now = time.time()
        roundtrip_time = time_now - start_time
        
        if status == 521:
            xlog.warn("X-tunnel server is down, try get new server.")
            g.server_host = None
            await self.stop()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, proxy_session.login_process)
            return False
        
        if status != 200:
            xlog.warn("roundtrip status:%d transfer_no:%d", status, transfer_no)
            async with self.lock:
                if transfer_no in self.transfer_list:
                    self.transfer_list[transfer_no]["stat"] = "timeout"
            await asyncio.sleep(1)
            return False
        
        content_length = 0
        if response and hasattr(response, 'headers'):
            cl = response.headers.get(b"Content-Length", b"0")
            try:
                content_length = int(cl)
            except Exception:
                pass
        content_len = len(content)
        if content_len < 6 or (content_length and content_length != content_len):
            xlog.warn("roundtrip time:%f transfer_no:%d send:%d recv:%d Head:%d",
                      roundtrip_time, transfer_no, send_data_len, content_len, content_length)
            async with self.lock:
                if transfer_no in self.transfer_list:
                    self.transfer_list[transfer_no]["stat"] = "timeout"
            return False
        
        try:
            content = decrypt_data(content)
            payload = base_container.ReadBuffer(content)
            
            magic, version, pack_type = struct.unpack("<cBB", payload.get(3))
            if magic != b"P" or version != protocol_version or pack_type not in [2, 3]:
                xlog.warn("invalid response head magic:%s version:%d pack_type:%d",
                          magic, version, pack_type)
                async with self.lock:
                    if transfer_no in self.transfer_list:
                        self.transfer_list[transfer_no]["stat"] = "timeout"
                return False
            
            if pack_type == 3:
                error_code, message_len = struct.unpack("<BH", payload.get(3))
                message = payload.get(message_len)
                xlog.warn("server error code:%d msg:%s", error_code, message)
                
                if error_code == 1:
                    xlog.warn("no quota")
                    await self.stop()
                    return False
                elif error_code == 2:
                    xlog.warn("roundtrip time:%f transfer_no:%d send:%d recv:%d unpack_error:%s",
                              roundtrip_time, transfer_no, send_data_len, content_len, message)
                    async with self.lock:
                        if transfer_no in self.transfer_list:
                            self.transfer_list[transfer_no]["stat"] = "timeout"
                    return False
                elif error_code == 3:
                    xlog.warn("session not exist, reset")
                    await self.reset()
                    return False
                
                async with self.lock:
                    if transfer_no in self.transfer_list:
                        self.transfer_list[transfer_no]["stat"] = "timeout"
                return False
            
            server_time, time_cost, server_send_pool_size, data_len, ack_len, \
                rcvd_no_len, sent_no_len, unack_snd_sn_len, ext_len \
                = struct.unpack("<dIIIIIIII", payload.get(40))
            
            head_len = content_len - data_len - ack_len - rcvd_no_len - sent_no_len - unack_snd_sn_len - ext_len
            if head_len < 3 + 40:
                xlog.warn("no:%d recv_len:%d data:%d ack:%d head:%d",
                          transfer_no, content_len, data_len, ack_len, head_len)
                async with self.lock:
                    if transfer_no in self.transfer_list:
                        self.transfer_list[transfer_no]["stat"] = "timeout"
                return False
            
            data = payload.get_buf(data_len)
            ack = payload.get_buf(ack_len)
            rcvd_no_list = payload.get_buf(rcvd_no_len)
            sent_no_list = payload.get_buf(sent_no_len)
            unack_snd_sn = payload.get_buf(unack_snd_sn_len)
            ext = payload.get_buf(ext_len)
            
            if len(payload) > 32:
                checksum_str = utils.to_str(payload.get(32).tobytes())
                checksum = hashlib.md5(bytes(content[:-32])).hexdigest()
                if checksum != checksum_str:
                    xlog.warn("checksum error:%s %s", checksum_str, checksum)
                    async with self.lock:
                        if transfer_no in self.transfer_list:
                            self.transfer_list[transfer_no]["stat"] = "timeout"
                    return False
            
            rtt = roundtrip_time - (time_cost / 1000.0)
            speed = (send_data_len + content_len + 400) / rtt if rtt > 0 else 0
            
            if roundtrip_time < self.server_time_deviation:
                new_offset = server_time - time_now
                xlog.info("adjust server time offset:%f->%f, deviation:%f->%f",
                          self.server_time_offset, new_offset,
                          self.server_time_deviation, roundtrip_time)
                self.server_time_offset = new_offset
                self.server_time_deviation = roundtrip_time
            
            if rtt > 8000 and hasattr(g, 'stat'):
                g.stat["slow_roundtrip"] += 1
            
            xlog.debug("no:%d road_time:%f snd:%d rcv:%d s_pool:%d on_road:%d target:%d speed:%d",
                       transfer_no, rtt, send_data_len, content_len,
                       server_send_pool_size, self.on_road_num,
                       self.target_on_roads, speed)
            
            self.last_receive_time = time.time()
            
            async with self.lock:
                if transfer_no in self.transfer_list:
                    del self.transfer_list[transfer_no]
            
            await self.round_trip_process(data, ack, rcvd_no_list, sent_no_list, unack_snd_sn, server_time)
            await self.check_upload_not_acked(server_time)
            
            if len(self.conn_list) == 0:
                self.target_on_roads = 0
            elif content_len >= self.max_payload:
                self.target_on_roads = min(self.concurent_thread_num - self.min_on_road, self.target_on_roads + 10)
            elif data_len <= 200:
                self.target_on_roads = max(self.min_on_road, self.target_on_roads - 5)
            
            self.trigger_more()
            self.wait_queue.notify()
            return True
            
        except Exception as e:
            xlog.exception("roundtrip process error: %r", e)
            async with self.lock:
                if transfer_no in self.transfer_list:
                    self.transfer_list[transfer_no]["stat"] = "timeout"
            return False
    
    async def check_upload_not_acked(self, server_time: float) -> None:
        server_local_time = server_time - self.server_time_offset
        if self.server_time_deviation > self.server_time_max_deviation:
            return
        
        timeout_num = 0
        async with self.lock:
            for no, data_info in self.transfer_list.items():
                if data_info["stat"] == "timeout":
                    continue
                
                if not data_info["server_received"] and \
                        server_local_time - data_info["start_time"] > self.send_timeout_retry:
                    data_info["stat"] = "timeout"
                    xlog.warn("check_upload_not_acked found transfer_no:%d upload timeout:%f",
                              no, server_local_time - data_info["start_time"])
                    timeout_num += 1
                    continue
                
                if data_info["server_sent"] and server_time - data_info["server_sent"] > self.send_timeout_retry:
                    data_info["stat"] = "timeout"
                    xlog.warn("check_upload_not_acked found transfer_no:%d down timeout:%f",
                              no, server_time - data_info["server_sent"])
                    timeout_num += 1
        
        if timeout_num:
            self.target_on_roads = min(self.concurent_thread_num - self.min_on_road, self.target_on_roads + timeout_num)
            self.trigger_more()
    
    async def get_upload_data(self, work_id: int) -> Optional[Dict[str, Any]]:
        time_now = time.time()
        
        async with self.lock:
            wrong_sn = []
            for sn, data_info in self.transfer_list.items():
                if data_info.get("session_id") != self.session_id:
                    wrong_sn.append(sn)
                    continue
                
                if data_info["stat"] == "timeout":
                    xlog.warn("retry transfer_no:%d t:%f", sn, time_now - data_info["start_time"])
                    data_info["stat"] = "retry"
                    data_info["retry"] += 1
                    data_info["start_time"] = time_now
                    return data_info
            
            for sn in wrong_sn:
                del self.transfer_list[sn]
        
        data, ack, download_timeout = await self.get_send_data(work_id)
        
        async with self.lock:
            self.last_transfer_no += 1
            transfer_no = self.last_transfer_no
        
        start_time = time.time()
        info = {
            "session_id": self.session_id,
            "transfer_no": transfer_no,
            "stat": "request",
            "server_received": False,
            "server_sent": False,
            "start_time": start_time,
            "server_timeout": self.roundtrip_timeout,
            "send_data": bytes(data) if data else b"",
            "send_ack": bytes(ack) if ack else b"",
            "download_timeout": bytes(download_timeout) if download_timeout else b"",
            "request_session_id": self.session_id,
            "retry": 0,
        }
        
        async with self.lock:
            self.transfer_list[transfer_no] = info
        
        return info
    
    async def get_send_data(self, work_id: int) -> Tuple[Any, Any, Any]:
        force = False
        
        while self.running:
            data = await self.get_data(work_id)
            down_sn_timeout_list_pack = await self.get_down_sn_timeout_list_pack()
            
            if data or len(down_sn_timeout_list_pack) > 4:
                force = True
            
            if self.on_road_num < self.target_on_roads:
                force = True
            
            ack = await self.get_ack(force=force)
            
            if force or ack:
                return data, ack, down_sn_timeout_list_pack
            
            await self.wait_queue.wait(timeout=1)
        
        return b"", b"", b""
    
    async def get_data(self, work_id: int) -> Any:
        time_now = time.time()
        buf = base_container.WriteBuffer()
        
        async with self.lock:
            for sn in self.wait_ack_send_list:
                pk = self.wait_ack_send_list[sn]
                if isinstance(pk, str):
                    continue
                
                payload, send_time = pk
                if time_now - send_time > self.resend_timeout:
                    if hasattr(g, 'stat'):
                        g.stat["resend"] += 1
                    buf.append(struct.pack("<II", sn, len(payload)))
                    buf.append(payload)
                    self.wait_ack_send_list[sn] = (payload, time_now)
                    if len(buf) > self.max_payload:
                        return buf
            
            pool_size = len(self.send_buffer)
            if pool_size > self.max_payload or \
               (pool_size > 0 and time.time() - self.oldest_received_time > self.send_delay):
                
                payload_result, sn = await self.send_buffer.get()
                if payload_result and sn > 0:
                    if isinstance(payload_result, base_container.WriteBuffer):
                        payload_bytes = payload_result.to_bytes()
                    else:
                        payload_bytes = bytes(payload_result)
                    
                    self.wait_ack_send_list[sn] = (payload_bytes, time_now)
                    buf.append(struct.pack("<II", sn, len(payload_bytes)))
                    buf.append(payload_bytes)
                    
                    if len(self.send_buffer) == 0:
                        self.oldest_received_time = 0
                    
                    if len(buf) > self.max_payload:
                        return buf
        
        return buf
    
    async def get_ack(self, force: bool = False) -> Any:
        time_now = time.time()
        
        if force or \
           (self.last_receive_time > self.last_send_time and
            time_now - self.last_receive_time > self.ack_delay):
            
            buf = base_container.WriteBuffer()
            async with self.lock:
                buf.append(struct.pack("<I", self.receive_process.next_sn - 1))
                for sn in self.receive_process.block_list:
                    buf.append(struct.pack("<I", sn))
            return buf
        
        return b""
    
    async def get_down_sn_timeout_list_pack(self) -> Any:
        buf = base_container.WriteBuffer()
        if self.server_time_deviation > self.server_time_max_deviation:
            return buf
        
        server_time = int(time.time() + self.server_time_offset)
        timeout_list = await self.receive_process.get_timeout_list(server_time, self.server_download_timeout_retry)
        for sn in timeout_list:
            buf.append(struct.pack("<I", sn))
        buf.insert(struct.pack("<I", len(timeout_list)))
        return buf
    
    async def round_trip_process(self, data: Any, ack: Any,
                                  rcvd_no_list: Any, sent_no_list: Any,
                                  unack_snd_sn: Any, server_time: float) -> None:
        while len(data):
            sn, plen = struct.unpack("<II", data.get(8))
            pdata = data.get_buf(plen)
            await self.receive_process.put(sn, pdata)
        
        await self.ack_process(ack)
        
        await self.process_server_received_transfer_no(rcvd_no_list, sent_no_list, server_time)
        await self.process_server_unacked_sent_sn(unack_snd_sn)
    
    async def ack_process(self, ack: Any) -> None:
        async with self.lock:
            try:
                last_ack = struct.unpack("<I", ack.get(4))[0]
                
                while len(ack):
                    sn = struct.unpack("<I", ack.get(4))[0]
                    if sn in self.wait_ack_send_list:
                        self.wait_ack_send_list[sn] = "acked"
                
                for sn in self.wait_ack_send_list:
                    if sn > last_ack:
                        continue
                    if self.wait_ack_send_list[sn] == "acked":
                        continue
                    self.wait_ack_send_list[sn] = "acked"
                
                while (self.ack_send_continue_sn + 1) in self.wait_ack_send_list and \
                      self.wait_ack_send_list[self.ack_send_continue_sn + 1] == "acked":
                    self.ack_send_continue_sn += 1
                    del self.wait_ack_send_list[self.ack_send_continue_sn]
            except Exception as e:
                xlog.exception("ack_process: %r", e)
    
    async def process_server_received_transfer_no(self, rcvd_no_list: Any,
                                                   sent_no_list: Any, server_time: float) -> None:
        async with self.lock:
            try:
                server_received_next_no = struct.unpack("<I", rcvd_no_list.get(4))[0]
                server_sent_next_no = struct.unpack("<I", sent_no_list.get(4))[0]
                
                for no, info in self.transfer_list.items():
                    if no < server_received_next_no:
                        info["server_received"] = True
                    if no < server_sent_next_no:
                        info["server_sent"] = server_time
                
                server_unordered_received_no_num = struct.unpack("<I", rcvd_no_list.get(4))[0]
                for i in range(server_unordered_received_no_num):
                    no, t = struct.unpack("<Id", rcvd_no_list.get(12))
                    if no in self.transfer_list:
                        self.transfer_list[no]["server_received"] = t
                
                server_unordered_sent_no_num = struct.unpack("<I", sent_no_list.get(4))[0]
                for i in range(server_unordered_sent_no_num):
                    no, t = struct.unpack("<Id", sent_no_list.get(12))
                    if no in self.transfer_list:
                        self.transfer_list[no]["server_sent"] = t
            except Exception as e:
                xlog.debug("process_server_received error: %r", e)
    
    async def process_server_unacked_sent_sn(self, data: Any) -> None:
        if self.server_time_deviation > self.server_time_max_deviation:
            return
        
        server_time = time.time() + self.server_time_offset
        
        try:
            sn_num = struct.unpack("<I", data.get(4))[0]
            for i in range(sn_num):
                sn, t = struct.unpack("<Id", data.get(12))
                if self.receive_process.is_received(sn):
                    continue
                if server_time - t > self.server_download_timeout_retry:
                    await self.receive_process.mark_sn_timeout(sn, t, server_time)
        except Exception as e:
            xlog.debug("process_server_unacked error: %r", e)
    
    async def timeout_checker(self) -> None:
        try:
            while self.running:
                await asyncio.sleep(2)
                await self._check_timeout()
        except asyncio.CancelledError:
            pass
    
    async def _check_timeout(self) -> None:
        now = time.time()
        timeout_threshold = now - self.send_timeout_retry
        
        async with self.lock:
            timeout_num = 0
            for sn, data_info in list(self.transfer_list.items()):
                if data_info["stat"] not in ["timeout", "done"]:
                    if data_info["start_time"] + data_info.get("server_timeout", 30) < timeout_threshold:
                        data_info["stat"] = "timeout"
                        xlog.warn("transfer %d timeout", sn)
                        timeout_num += 1
            
            if timeout_num:
                self.target_on_roads = min(self.concurent_thread_num - self.min_on_road,
                                          self.target_on_roads + timeout_num)
                self.trigger_more()
    
    async def download_data_processor(self, data: bytes) -> None:
        try:
            payload = base_container.ReadBuffer(data)
            while len(payload):
                conn_id, payload_len = struct.unpack("<II", payload.get(8))
                conn_payload = payload.get_buf(payload_len)
                
                if conn_id not in self.conn_list:
                    xlog.debug("conn %d not exist", conn_id)
                    continue
                
                conn = self.conn_list[conn_id]
                await conn.put_cmd_data(conn_payload)
        except Exception as e:
            xlog.exception("download_data_processor: %r", e)
    
    async def create_conn(self, sock: Any, host: Union[str, bytes], port: int,
                          log: bool = False) -> Optional[int]:
        if not self.running:
            xlog.debug("session not running")
            await asyncio.sleep(1)
            return None
        
        async with self.lock:
            self.last_conn_id += 2
            conn_id = self.last_conn_id
        
        if isinstance(host, str):
            host = host.encode("ascii")
        
        seq = 0
        cmd_type = 0
        sock_type = 0
        data = struct.pack("<IBBH", seq, cmd_type, sock_type, len(host)) + host + struct.pack("<H", port)
        await self.send_conn_data(conn_id, data)
        
        conn = AsyncConn(self, conn_id, sock, host.decode('ascii', errors='replace'), port, xlog,
                         windows_size=self.windows_size, windows_ack=self.windows_ack, is_client=True)
        async with self.lock:
            self.conn_list[conn_id] = conn
        
        self.target_on_roads = min(self.concurent_thread_num - self.min_on_road, self.target_on_roads + 2)
        self.trigger_more()
        
        await conn.start()
        
        if log:
            xlog.info("Connect to %s:%d conn:%d", host, port, conn_id)
        
        return conn_id
    
    async def send_conn_data(self, conn_id: int, data: bytes) -> None:
        if not self.running:
            return
        
        buf = base_container.WriteBuffer()
        buf.append(struct.pack("<II", conn_id, len(data)))
        buf.append(data)
        await self.send_buffer.add(buf.to_bytes())
        
        if self.oldest_received_time == 0:
            self.oldest_received_time = time.time()
        elif len(self.send_buffer) > self.max_payload:
            self.wait_queue.notify()
    
    async def on_conn_data(self, conn_id: int, data: bytes) -> None:
        async with self.lock:
            if conn_id not in self.conn_list:
                return
            conn = self.conn_list[conn_id]
        
        await conn.put_cmd_data(data)
    
    async def remove_conn_async(self, conn_id: int) -> None:
        async with self.lock:
            if conn_id in self.conn_list:
                del self.conn_list[conn_id]
        
        if len(self.conn_list) == 0:
            self.target_on_roads = 0
    
    async def close_all_connections(self) -> None:
        async with self.lock:
            for conn_id, conn in list(self.conn_list.items()):
                try:
                    await conn.stop_async("session_stop")
                except Exception:
                    pass
            self.conn_list.clear()
    
    async def login_session(self) -> bool:
        if not g.server_host:
            return False
        
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                magic = b"P"
                pack_type = 1
                protocol_version = g.protocol_version if hasattr(g, 'protocol_version') else 1
                
                head = struct.pack("<cBB8sIHIIHH", magic, protocol_version, pack_type,
                                  self.session_id,
                                  self.max_payload, int(self.send_delay * 1000), self.windows_size,
                                  int(self.windows_ack), int(self.resend_timeout * 1000), int(self.ack_delay * 1000))
                
                login_account = g.config.login_account if self.config and hasattr(self.config, 'login_account') else ""
                login_password = g.config.login_password if self.config and hasattr(self.config, 'login_password') else ""
                
                head += struct.pack("<H", len(login_account)) + utils.to_bytes(login_account)
                head += struct.pack("<H", len(login_password)) + utils.to_bytes(login_password)
                
                extra_info = self.get_login_extra_info()
                head += struct.pack("<H", len(extra_info)) + utils.to_bytes(extra_info)
                
                upload_post_data = encrypt_data(head)
                
                loop = asyncio.get_event_loop()
                content, status, response = await loop.run_in_executor(
                    None,
                    lambda: g.http_client.request(
                        method="POST",
                        host=g.server_host,
                        path="/data",
                        data=upload_post_data,
                        timeout=self.network_timeout
                    )
                )
                
                time_cost = time.time() - start_time
                
                if status == 521:
                    g.server_host = None
                    return False
                
                if status != 200:
                    xlog.warn("login status: %d", status)
                    await asyncio.sleep(1)
                    continue
                
                if len(content) < 6:
                    xlog.warn("login response too short")
                    await asyncio.sleep(1)
                    continue
                
                return self._parse_login_response(content)
                
            except Exception as e:
                xlog.debug("login error: %r", e)
                await asyncio.sleep(1)
        
        return False
    
    def _parse_login_response(self, content: bytes) -> bool:
        try:
            info = decrypt_data(content)
            magic, protocol_version, pack_type, res, message_len = struct.unpack("<cBBBH", info[:6])
            message = info[6:]
            if isinstance(message, memoryview):
                message = message.tobytes()
            
            protocol_version_expected = g.protocol_version if hasattr(g, 'protocol_version') else 1
            if magic != b"P" or protocol_version != protocol_version_expected or pack_type != 1:
                xlog.error("login_session head error: magic:%s version:%d/%d pack_type:%d",
                           magic, protocol_version, protocol_version_expected, pack_type)
                return False
            
            if res != 0:
                g.last_api_error = "session server login fail, code:%d msg:%s" % (res, message)
                xlog.warn("login fail, res:%d msg:%s", res, message)
                return False
            
            try:
                msg_info = json.loads(message)
                if msg_info.get("full_log"):
                    xlog.debug("keep full log")
                    keep_log(temp=True)
            except Exception as e:
                xlog.warn("login_session %s json error:%r", message, e)
            
            if hasattr(g, 'http_client') and hasattr(g.http_client, 'set_session_host'):
                g.http_client.set_session_host(g.server_host)
            
            g.last_api_error = ""
            xlog.info("login success, session_id: %s", self.session_id)
            return True
        except Exception as e:
            xlog.debug("_parse_login_response error: %r", e)
            return False
    
    @staticmethod
    def get_login_extra_info() -> str:
        data = {
            "version": getattr(g, 'xxnet_version', 'unknown'),
            "system": getattr(g, 'system', 'unknown'),
            "device": getattr(g, 'client_uuid', 'unknown')
        }
        return json.dumps(data)
    
    def status(self) -> str:
        self.traffic_speed_calculation()
        out = f"AsyncProxySession:\n"
        out += f" session_id: {utils.to_str(self.session_id)}\n"
        out += f" running: {self.running}\n"
        out += f" connections: {len(self.conn_list)}\n"
        out += f" last_send_time: {time.time() - self.last_send_time:.1f}s ago\n"
        out += f" last_receive_time: {time.time() - self.last_receive_time:.1f}s ago\n"
        out += f" upload: {traffic_readable(self.traffic_upload)}\n"
        out += f" download: {traffic_readable(self.traffic_download)}\n"
        out += f" upload_speed: {traffic_readable(self.upload_speed)}/s\n"
        out += f" download_speed: {traffic_readable(self.download_speed)}/s\n"
        out += f" target_on_roads: {self.target_on_roads}\n"
        out += f" on_road_num: {self.on_road_num}\n"
        out += f" transfer_list: {len(self.transfer_list)}\n"
        out += f" server_time_offset: {self.server_time_offset}\n"
        out += f" server_time_deviation: {self.server_time_deviation}\n"
        out += self.wait_queue.status() if hasattr(self.wait_queue, 'status') else ""
        out += self.send_buffer.status()
        out += self.receive_process.status()
        out += self.connection_pipe.status()
        for conn_id in self.conn_list:
            out += self.conn_list[conn_id].status()
        return out
    
    async def check_upload(self) -> Optional[bool]:
        if len(self.send_buffer) > 0:
            self.wait_queue.notify()
            return True
        return None
    
    def get_stat(self, stat_type: str = "second") -> Dict[str, Any]:
        self.traffic_speed_calculation()
        
        res = {}
        res["global"] = {
            "handle_num": getattr(getattr(g, 'socks5_server', None), 'handler', type('', (), {'handle_num': 0})()).handle_num,
            "roundtrip_num": getattr(g, 'stat', {}).get("roundtrip_num", 0),
            "slow_roundtrip": getattr(g, 'stat', {}).get("slow_roundtrip", 0),
            "timeout_roundtrip": getattr(g, 'stat', {}).get("timeout_roundtrip", 0),
            "resend": getattr(g, 'stat', {}).get("resend", 0),
            "speed": "Up: %s/s / Down: %s/s" % (traffic_readable(self.upload_speed), traffic_readable(self.download_speed)),
            "total_traffics": "Up: %s / Down: %s" % (traffic_readable(self.traffic_upload), traffic_readable(self.traffic_download))
        }
        return res


_login_lock = asyncio.Lock()


async def async_login_process() -> bool:
    if not g.session:
        return False
    
    async with _login_lock:
        if not (g.config and g.config.login_account and g.config.login_password):
            xlog.debug("x-tunnel no account")
            return False
        
        if not g.server_host:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, proxy_session.request_balance)
            if not g.server_host:
                xlog.debug("no server host after request_balance")
                return False
        
        if hasattr(g, 'session') and g.session and hasattr(g.session, 'last_send_time'):
            if g.session.running and time.time() - g.session.last_send_time > 300 - 5:
                xlog.warn("session timeout, reset")
                await g.session.reset()
        
        if not g.session.running:
            return await g.session.start()
    
    return True


async def async_create_conn(sock: Any, host: Union[str, bytes], port: int, log: bool = False) -> Optional[int]:
    if not (g.config and g.config.login_account and g.config.login_password):
        await asyncio.sleep(1)
        return None
    
    for _ in range(3):
        if await async_login_process():
            break
        await asyncio.sleep(1)
    
    if g.session and g.session.running:
        return await g.session.create_conn(sock, host, port, log)
    return None
