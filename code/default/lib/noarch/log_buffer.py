#!/usr/bin/env python3
# coding:utf-8
"""
Logging infrastructure backed by stdlib logging with web UI buffer support.

Replaces the former xlog.py.  All underlying logging uses Python's standard
``logging`` module.  A ``BufferHandler`` is provided so the web UI can
retrieve recent log lines.

Usage::

    from log_buffer import getLogger
    xlog = getLogger("module_name")
    xlog.info("hello %s", name)

    # enable web UI log buffer
    from log_buffer import getLogger
    xlog = getLogger("module_name", buffer_size=200)

    # retrieve buffered lines (web UI)
    data = xlog.get_last_lines(50)
"""

import logging
import logging.handlers
import os
import sys
import json
import threading
from datetime import datetime


def _bytes2str(args):
    if not isinstance(args, tuple):
        return args
    result = []
    for a in args:
        if isinstance(a, bytes):
            result.append(a.decode('utf-8', errors='replace'))
        elif isinstance(a, (tuple, list)):
            converted = [
                x.decode('utf-8', errors='replace') if isinstance(x, bytes) else x
                for x in a
            ]
            result.append(type(a)(converted))
        else:
            result.append(a)
    return tuple(result)


class BufferHandler(logging.Handler):
    def __init__(self, buffer_size=0):
        super().__init__()
        self._buffer = {}
        self._last_no = 0
        self._buffer_size = buffer_size
        self._handler_lock = threading.RLock()

    @property
    def buffer(self):
        return self._buffer

    @property
    def last_no(self):
        return self._last_no

    @property
    def buffer_size(self):
        return self._buffer_size

    def emit(self, record):
        try:
            msg = self.format(record)
            with self._handler_lock:
                if self._buffer_size:
                    self._last_no += 1
                    self._buffer[self._last_no] = msg + '\n'
                    if len(self._buffer) > self._buffer_size:
                        del self._buffer[self._last_no - self._buffer_size]
        except Exception:
            pass

    def get_last_lines(self, max_lines):
        with self._handler_lock:
            buf_len = len(self._buffer)
            if buf_len == 0:
                return '{}'
            if buf_len > max_lines:
                first_no = self._last_no - max_lines
            else:
                first_no = self._last_no - buf_len + 1
            jd = {}
            for i in range(first_no, self._last_no + 1):
                v = self._buffer.get(i, '')
                jd[i] = v if isinstance(v, str) else str(v)
            return json.dumps(jd)

    def get_new_lines(self, from_no):
        with self._handler_lock:
            jd = {}
            if self._buffer:
                first_no = self._last_no - len(self._buffer) + 1
                if from_no < first_no:
                    from_no = first_no
                if self._last_no >= from_no:
                    for i in range(from_no, self._last_no + 1):
                        v = self._buffer.get(i, '')
                        jd[i] = v if isinstance(v, str) else str(v)
            return json.dumps(jd)

    def set_buffer_size(self, size):
        with self._handler_lock:
            self._buffer_size = size
            buf_len = len(self._buffer)
            if buf_len > size:
                for i in range(self._last_no - buf_len, self._last_no - size):
                    self._buffer.pop(i, None)


class _WarningLogHandler(logging.Handler):
    def __init__(self, filepath):
        super().__init__()
        self._fd = open(filepath, "a")

    def emit(self, record):
        if record.levelno < logging.WARNING:
            return
        try:
            msg = self.format(record)
            self._fd.write(msg + '\n')
            self._fd.flush()
        except Exception:
            pass

    def close(self):
        super().close()
        try:
            self._fd.close()
        except Exception:
            pass


_FILE_FMT = logging.Formatter(
    '%(asctime)s - [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
_CONSOLE_FMT = logging.Formatter(
    '%(asctime)s [%(name)s][%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')

_registry = {}
_start_log_info = {}
_warning_log_handlers = {}
_file_handlers = {}
_full_log = False
_logger_instances = {}


class LoggerProxy:
    __slots__ = ('_lb_name', '_lb_logger', '_lb_buffer_handler')

    def __init__(self, name, py_logger):
        object.__setattr__(self, '_lb_name', name)
        object.__setattr__(self, '_lb_logger', py_logger)
        object.__setattr__(self, '_lb_buffer_handler', None)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_lb_logger'), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, '_lb_logger'), name, value)

    def debug(self, fmt, *args, **kwargs):
        object.__getattribute__(self, '_lb_logger').debug(fmt, *_bytes2str(args), **kwargs)

    def info(self, fmt, *args, **kwargs):
        object.__getattribute__(self, '_lb_logger').info(fmt, *_bytes2str(args), **kwargs)

    def warning(self, fmt, *args, **kwargs):
        object.__getattribute__(self, '_lb_logger').warning(fmt, *_bytes2str(args), **kwargs)

    def warn(self, fmt, *args, **kwargs):
        self.warning(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        object.__getattribute__(self, '_lb_logger').error(fmt, *_bytes2str(args), **kwargs)

    def exception(self, fmt, *args, **kwargs):
        object.__getattribute__(self, '_lb_logger').exception(fmt, *_bytes2str(args), **kwargs)

    def critical(self, fmt, *args, **kwargs):
        object.__getattribute__(self, '_lb_logger').critical(fmt, *_bytes2str(args), **kwargs)

    @property
    def buffer(self):
        h = object.__getattribute__(self, '_lb_buffer_handler')
        return h.buffer if h else {}

    @property
    def last_no(self):
        h = object.__getattribute__(self, '_lb_buffer_handler')
        return h.last_no if h else 0

    @property
    def buffer_size(self):
        h = object.__getattribute__(self, '_lb_buffer_handler')
        return h.buffer_size if h else 0

    @property
    def buffer_lock(self):
        h = object.__getattribute__(self, '_lb_buffer_handler')
        return h._handler_lock if h else threading.RLock()

    def get_last_lines(self, max_lines):
        h = object.__getattribute__(self, '_lb_buffer_handler')
        return h.get_last_lines(max_lines) if h else '{}'

    def get_new_lines(self, from_no):
        h = object.__getattribute__(self, '_lb_buffer_handler')
        return h.get_new_lines(from_no) if h else '{}'

    def set_buffer(self, buffer_size):
        name = object.__getattribute__(self, '_lb_name')
        logger = object.__getattribute__(self, '_lb_logger')
        old = object.__getattribute__(self, '_lb_buffer_handler')
        if old:
            logger.removeHandler(old)
        handler = BufferHandler(buffer_size)
        handler.setFormatter(_FILE_FMT)
        logger.addHandler(handler)
        object.__setattr__(self, '_lb_buffer_handler', handler)
        _registry[name] = handler

    def set_file(self, file_name):
        name = object.__getattribute__(self, '_lb_name')
        logger = object.__getattribute__(self, '_lb_logger')
        old = _file_handlers.pop(name, None)
        if old:
            logger.removeHandler(old)
        handler = logging.handlers.RotatingFileHandler(
            file_name, maxBytes=1024 * 1024, backupCount=1)
        handler.setFormatter(_FILE_FMT)
        logger.addHandler(handler)
        _file_handlers[name] = handler

    def log_to_file(self, file_name):
        self.set_file(file_name)

    def setLevel(self, level):
        logger = object.__getattribute__(self, '_lb_logger')
        if isinstance(level, str):
            level_map = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARN": logging.WARNING,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "FATAL": logging.CRITICAL,
            }
            py_level = level_map.get(level)
            if py_level is not None:
                logger.setLevel(py_level)
                return
        logger.setLevel(level)

    @property
    def min_level(self):
        return object.__getattribute__(self, '_lb_logger').level

    @min_level.setter
    def min_level(self, value):
        object.__getattribute__(self, '_lb_logger').setLevel(value)

    def reset_log_files(self):
        name = object.__getattribute__(self, '_lb_name')
        logger = object.__getattribute__(self, '_lb_logger')
        info = _start_log_info.pop(name, None)
        if info:
            handler, fd = info
            logger.removeHandler(handler)
            if fd:
                fd.close()

    def keep_logs(self):
        pass


class null:
    @staticmethod
    def debug(fmt, *args, **kwargs):
        pass

    @staticmethod
    def info(fmt, *args, **kwargs):
        pass

    @staticmethod
    def warn(fmt, *args, **kwargs):
        pass

    @staticmethod
    def warning(fmt, *args, **kwargs):
        pass

    @staticmethod
    def error(fmt, *args, **kwargs):
        pass

    @staticmethod
    def exception(fmt, *args, **kwargs):
        pass


def getLogger(name=None, buffer_size=0, file_name=None, roll_num=1,
              log_path=None, save_start_log=0, save_warning_log=False):
    global _full_log

    if name is None:
        name = "default"
    if isinstance(name, bytes):
        name = name.decode('utf-8')

    if name in _logger_instances:
        return _logger_instances[name]

    py_logger = logging.getLogger(name)
    py_logger.propagate = False
    py_logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(_CONSOLE_FMT)
    py_logger.addHandler(console_handler)

    proxy = LoggerProxy(name, py_logger)

    if file_name:
        file_handler = logging.handlers.RotatingFileHandler(
            file_name, maxBytes=1024 * 1024, backupCount=roll_num)
        file_handler.setFormatter(_FILE_FMT)
        py_logger.addHandler(file_handler)
        _file_handlers[name] = file_handler

    if log_path and save_start_log:
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        fn = os.path.join(log_path, "start_log_%s_%s.log" % (name, time_str))
        fd = open(fn, "w")
        handler = logging.StreamHandler(fd)
        handler.setFormatter(_FILE_FMT)
        py_logger.addHandler(handler)
        _start_log_info[name] = (handler, fd)
        if os.path.exists(os.path.join(log_path, "keep_log.txt")):
            _full_log = True

    if log_path and save_warning_log:
        fn = os.path.join(log_path, "%s_warning.log" % name)
        handler = _WarningLogHandler(fn)
        handler.setFormatter(_FILE_FMT)
        py_logger.addHandler(handler)
        _warning_log_handlers[name] = handler

    if buffer_size:
        buffer_handler = BufferHandler(buffer_size)
        buffer_handler.setFormatter(_FILE_FMT)
        py_logger.addHandler(buffer_handler)
        object.__setattr__(proxy, '_lb_buffer_handler', buffer_handler)
        _registry[name] = buffer_handler

    _logger_instances[name] = proxy
    return proxy


def reset_log_files():
    for name, (handler, fd) in list(_start_log_info.items()):
        py_logger = logging.getLogger(name)
        py_logger.removeHandler(handler)
        if fd:
            fd.close()
    _start_log_info.clear()


def keep_log(temp=False):
    global _full_log
    if temp:
        _full_log = True


_default_logger = None


def _get_default():
    global _default_logger
    if _default_logger is None:
        _default_logger = getLogger("default")
    return _default_logger


def debug(fmt, *args, **kwargs):
    _get_default().debug(fmt, *args, **kwargs)


def info(fmt, *args, **kwargs):
    _get_default().info(fmt, *args, **kwargs)


def warning(fmt, *args, **kwargs):
    _get_default().warning(fmt, *args, **kwargs)


def warn(fmt, *args, **kwargs):
    _get_default().warn(fmt, *args, **kwargs)


def error(fmt, *args, **kwargs):
    _get_default().error(fmt, *args, **kwargs)


def exception(fmt, *args, **kwargs):
    _get_default().exception(fmt, *args, **kwargs)


def critical(fmt, *args, **kwargs):
    _get_default().critical(fmt, *args, **kwargs)
