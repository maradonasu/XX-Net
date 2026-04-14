import os
import sys
import time
import logging
import logging.handlers
from datetime import datetime
import traceback
import threading
import json
import shutil
from os.path import join

string_types = str

import utils

CRITICAL = logging.CRITICAL
FATAL = logging.CRITICAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = logging.WARNING
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET

full_log = False


class _WebBufferHandler(logging.Handler):
    def __init__(self, logger_instance, buffer_size=0):
        super().__init__()
        self._logger_instance = logger_instance
        self._buffer_size = buffer_size

    def emit(self, record):
        try:
            msg = self.format(record)
            inst = self._logger_instance
            with inst.buffer_lock:
                if inst.buffer_size:
                    inst.last_no += 1
                    inst.buffer[inst.last_no] = msg + '\n'
                    buf_len = len(inst.buffer)
                    if buf_len > inst.buffer_size:
                        del inst.buffer[inst.last_no - inst.buffer_size]
        except Exception:
            pass


class _StartLogHandler(logging.Handler):
    def __init__(self, logger_instance, filepath, max_entries=0):
        super().__init__()
        self._logger_instance = logger_instance
        self._filepath = filepath
        self._fd = open(filepath, "w")
        self._count = 0
        self._max_entries = max_entries

    def emit(self, record):
        try:
            msg = self.format(record)
            self._fd.write(msg + '\n')
            self._fd.flush()
            self._count += 1
            inst = self._logger_instance
            if self._max_entries and self._count >= self._max_entries and not inst.keep_log and not full_log:
                self._fd.close()
                self._fd = None
        except Exception:
            pass


class _WarningLogHandler(logging.Handler):
    def __init__(self, filepath):
        super().__init__()
        self._filepath = filepath
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


class _ColorFormatter(logging.Formatter):
    def __init__(self, logger_instance):
        super().__init__()
        self._inst = logger_instance

    def format(self, record):
        dt = datetime.fromtimestamp(record.created)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
        level_name = record.levelname
        return '%s [%s][%s] %s' % (time_str, record.name, level_name, record.getMessage())


class _FileFormatter(logging.Formatter):
    def __init__(self):
        super().__init__()

    def format(self, record):
        dt = datetime.fromtimestamp(record.created)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
        level_name = record.levelname
        return '%s - [%s] %s' % (time_str, level_name, record.getMessage())


class Logger():
    def __init__(self, name, buffer_size=0, file_name=None, roll_num=1,
                 log_path=None, save_start_log=0, save_warning_log=False):
        self.name = str(name)
        self.buffer_lock = threading.RLock()
        self.buffer = {}
        self.buffer_size = buffer_size
        self.last_no = 0
        self.min_level = NOTSET
        self.roll_num = roll_num
        self.file_max_size = 1024 * 1024
        self._file_size = 0
        self._log_filename = None
        self._log_fd = None

        self._py_logger = logging.getLogger('xlog.' + self.name)
        self._py_logger.propagate = False
        self._py_logger.setLevel(logging.DEBUG)

        self.set_color()

        self.log_path = log_path
        self.save_start_log = save_start_log
        self.save_warning_log = save_warning_log
        self.start_log = None
        self._start_log_handler = None
        self._warning_log_handler = None
        self.warning_log_fn = None
        self.warning_log = None
        self.start_log_num = 0
        self.keep_log = False

        self._console_handler = None
        self._file_handler = None
        self._buffer_handler = None
        self._color_fmt = _ColorFormatter(self)
        self._file_fmt = _FileFormatter()

        self._setup_console_handler()

        if file_name:
            self.set_file(file_name)

        if log_path and save_start_log:
            now = datetime.now()
            time_str = now.strftime("%Y-%m-%d_%H-%M-%S")
            self.log_fn = os.path.join(log_path, "start_log_%s_%s.log" % (name, time_str))
            self.start_log = open(self.log_fn, "w")
            handler = _StartLogHandler(self, self.log_fn, save_start_log)
            handler.setFormatter(self._file_fmt)
            self._py_logger.addHandler(handler)
            self._start_log_handler = handler
        else:
            self.log_fn = None

        if log_path and os.path.exists(join(log_path, "keep_log.txt")):
            self.info("keep log")
            self.keep_log = True

        if log_path and save_warning_log:
            self.warning_log_fn = os.path.join(log_path, "%s_warning.log" % (name))
            self.warning_log = open(self.warning_log_fn, "a")
            handler = _WarningLogHandler(self.warning_log_fn)
            handler.setFormatter(self._file_fmt)
            self._py_logger.addHandler(handler)
            self._warning_log_handler = handler

        if buffer_size:
            self._buffer_handler = _WebBufferHandler(self, buffer_size)
            self._buffer_handler.setFormatter(self._file_fmt)
            self._py_logger.addHandler(self._buffer_handler)

    def _setup_console_handler(self):
        self._console_handler = logging.StreamHandler(sys.stderr)
        self._console_handler.setFormatter(self._color_fmt)
        self._console_handler.addFilter(lambda record: self._console_emit(record) or True)
        self._py_logger.addHandler(self._console_handler)

    def _console_emit(self, record):
        color = None
        if record.levelno >= logging.ERROR:
            color = self.err_color
        elif record.levelno >= logging.WARNING:
            color = self.warn_color
        elif record.levelno >= logging.DEBUG:
            color = self.debug_color

        try:
            self.set_console_color(color)
        except Exception:
            pass
        return False

    def set_buffer(self, buffer_size):
        with self.buffer_lock:
            self.buffer_size = buffer_size
            buf_len = len(self.buffer)
            if buf_len > self.buffer_size:
                for i in range(self.last_no - buf_len, self.last_no - self.buffer_size):
                    try:
                        del self.buffer[i]
                    except Exception:
                        pass

    def reset_log_files(self):
        if not (self.keep_log or full_log):
            if self.start_log:
                self.start_log.close()
                self.start_log = None

            if self._start_log_handler:
                self._py_logger.removeHandler(self._start_log_handler)
                self._start_log_handler = None

            if self.warning_log:
                self.warning_log.close()
                self.warning_log = None

            if self._warning_log_handler:
                self._py_logger.removeHandler(self._warning_log_handler)
                self._warning_log_handler = None

        if self.log_path and not self.keep_log:
            for filename in os.listdir(self.log_path):
                fp = os.path.join(self.log_path, filename)
                if not filename.endswith(".log") or fp == self.log_fn or not filename.startswith("start_log_%s" % self.name):
                    continue
                try:
                    os.remove(fp)
                except Exception:
                    pass

        if self.warning_log_fn and not self.keep_log:
            self.warning_log = open(self.warning_log_fn, "a")
            handler = _WarningLogHandler(self.warning_log_fn)
            handler.setFormatter(self._file_fmt)
            self._py_logger.addHandler(handler)
            self._warning_log_handler = handler

    def keep_logs(self):
        self.keep_log = True
        if not self.log_path:
            return

        with open(join(self.log_path, "keep_log.txt"), "w") as fd:
            fd.write(" ")

        if not self.start_log:
            now = datetime.now()
            time_str = now.strftime("%Y-%m-%d_%H-%M-%S")
            log_fn = os.path.join(self.log_path, "start_log_%s_%s.log" % (self.name, time_str))
            self.start_log = open(log_fn, "w")

    def setLevel(self, level):
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
            self.min_level = py_level
            self._py_logger.setLevel(py_level)
        else:
            print(("log level not support:%s", level))

    def set_color(self):
        self.err_color = None
        self.warn_color = None
        self.debug_color = None
        self.reset_color = None
        self.set_console_color = lambda x: None
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            if os.name == 'nt':
                self.err_color = 0x04
                self.warn_color = 0x06
                self.debug_color = 0x002
                self.reset_color = 0x07

                import ctypes
                SetConsoleTextAttribute = ctypes.windll.kernel32.SetConsoleTextAttribute
                GetStdHandle = ctypes.windll.kernel32.GetStdHandle
                self.set_console_color = lambda color: SetConsoleTextAttribute(GetStdHandle(-11), color)

            elif os.name == 'posix':
                self.err_color = '\033[31m'
                self.warn_color = '\033[33m'
                self.debug_color = '\033[32m'
                self.reset_color = '\033[0m'

                self.set_console_color = lambda color: sys.stderr.write(color)

    def set_file(self, file_name):
        self._log_filename = file_name
        if os.path.isfile(file_name):
            self._file_size = os.path.getsize(file_name)
            if self._file_size > self.file_max_size:
                self._roll_log()
                self._file_size = 0
        else:
            self._file_size = 0

        self._log_fd = open(file_name, "a+")

        if self._file_handler:
            self._py_logger.removeHandler(self._file_handler)

        self._file_handler = logging.StreamHandler(self._log_fd)
        self._file_handler.setFormatter(self._file_fmt)
        self._py_logger.addHandler(self._file_handler)

    def _roll_log(self):
        for i in range(self.roll_num, 1, -1):
            new_name = "%s.%d" % (self._log_filename, i)
            old_name = "%s.%d" % (self._log_filename, i - 1)
            if not os.path.isfile(old_name):
                continue
            shutil.move(old_name, new_name)

        shutil.move(self._log_filename, self._log_filename + ".1")

    def _log(self, level, fmt, *args, **kwargs):
        if self.min_level and level < self.min_level:
            return

        args = utils.bytes2str_only(args)
        msg = fmt % args if args else fmt

        dt = datetime.now()
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
        level_names = {
            logging.DEBUG: 'DEBUG',
            logging.INFO: 'INFO',
            logging.WARNING: 'WARNING',
            logging.ERROR: 'ERROR',
            logging.CRITICAL: 'CRITICAL',
        }
        level_name = level_names.get(level, 'UNKNOWN')
        string = '%s - [%s] %s\n' % (time_str, level_name, msg)

        self.buffer_lock.acquire()
        try:
            try:
                console_string = '%s [%s][%s] %s\n' % (time_str, self.name, level_name, msg)

                console_color = None
                if level >= logging.ERROR:
                    console_color = self.err_color
                elif level >= logging.WARNING:
                    console_color = self.warn_color
                elif level >= logging.DEBUG:
                    console_color = self.debug_color

                self.set_console_color(console_color)
                sys.stderr.write(console_string)
                self.set_console_color(self.reset_color)
            except Exception:
                pass

            if self._log_fd:
                self._log_fd.write(string)
                try:
                    self._log_fd.flush()
                except Exception:
                    pass

                self._file_size += len(string)
                if self._file_size > self.file_max_size:
                    self._log_fd.close()
                    self._log_fd = None
                    self._roll_log()
                    self._log_fd = open(self._log_filename, "w")
                    self._file_size = 0

            if self.start_log:
                self.start_log.write(string)
                try:
                    self.start_log.flush()
                except Exception:
                    pass
                self.start_log_num += 1

                if self.start_log_num > self.save_start_log and not self.keep_log and not full_log:
                    self.start_log.close()
                    self.start_log = None

            if self.warning_log and level >= logging.WARNING:
                self.warning_log.write(string)
                try:
                    self.warning_log.flush()
                except Exception:
                    pass

            if self.buffer_size:
                self.last_no += 1
                self.buffer[self.last_no] = string
                buf_len = len(self.buffer)
                if buf_len > self.buffer_size:
                    del self.buffer[self.last_no - self.buffer_size]
        except Exception as e:
            error_str = '%s - [%s]LOG_EXCEPT: %s, Except:%s<br> %s' % \
                        (time.ctime()[4:-5], level_name, msg, e, traceback.format_exc())
            self.last_no += 1
            self.buffer[self.last_no] = error_str
            buf_len = len(self.buffer)
            if buf_len > self.buffer_size:
                del self.buffer[self.last_no - self.buffer_size]
        finally:
            self.buffer_lock.release()

    def debug(self, fmt, *args, **kwargs):
        if self.min_level > DEBUG:
            return
        self._log(logging.DEBUG, fmt, *args, **kwargs)

    def info(self, fmt, *args, **kwargs):
        if self.min_level > INFO:
            return
        self._log(logging.INFO, fmt, *args)

    def warning(self, fmt, *args, **kwargs):
        if self.min_level > WARN:
            return
        self._log(logging.WARNING, fmt, *args, **kwargs)

    def warn(self, fmt, *args, **kwargs):
        self.warning(fmt, *args, **kwargs)

    def error(self, fmt, *args, **kwargs):
        if self.min_level > ERROR:
            return
        self._log(logging.ERROR, fmt, *args, **kwargs)

    def exception(self, fmt, *args, **kwargs):
        self.error(fmt, *args, **kwargs)
        self.error("Except stack:%s", traceback.format_exc(), **kwargs)

    def critical(self, fmt, *args, **kwargs):
        if self.min_level > CRITICAL:
            return
        self._log(logging.CRITICAL, fmt, *args, **kwargs)

    def get_last_lines(self, max_lines):
        self.buffer_lock.acquire()
        buf_len = len(self.buffer)
        if buf_len > max_lines:
            first_no = self.last_no - max_lines
        else:
            first_no = self.last_no - buf_len + 1

        jd = {}
        if buf_len > 0:
            for i in range(first_no, self.last_no + 1):
                jd[i] = utils.to_str(self.buffer[i])
        self.buffer_lock.release()
        return json.dumps(jd)

    def get_new_lines(self, from_no):
        self.buffer_lock.acquire()
        jd = {}
        first_no = self.last_no - len(self.buffer) + 1
        if from_no < first_no:
            from_no = first_no

        if self.last_no >= from_no:
            for i in range(from_no, self.last_no + 1):
                jd[i] = utils.to_str(self.buffer[i])
        self.buffer_lock.release()
        return json.dumps(jd)


class null():
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
    def exception(fmt, *args, **kwargs):
        pass


loggerDict = {}


def getLogger(name=None, buffer_size=0, file_name=None, roll_num=1,
              log_path=None, save_start_log=0, save_warning_log=False):
    global loggerDict, default_log
    if name is None:
        for n in loggerDict:
            name = n
            break
    if name is None:
        name = u"default"

    if not isinstance(name, string_types):
        raise TypeError('A logger name must be string or Unicode')
    if isinstance(name, bytes):
        name = name.decode('utf-8')

    if name in loggerDict:
        return loggerDict[name]
    else:
        logger_instance = Logger(name, buffer_size, file_name, roll_num, log_path, save_start_log, save_warning_log)
        loggerDict[name] = logger_instance
        default_log = logger_instance
        return logger_instance


def reset_log_files():
    for name, log in loggerDict.items():
        log.reset_log_files()


def keep_log(temp=False):
    global full_log
    if temp:
        full_log = True
    else:
        for name, log in loggerDict.items():
            log.keep_logs()


default_log = getLogger()


def debug(fmt, *args, **kwargs):
    default_log.debug(fmt, *args, **kwargs)


def info(fmt, *args, **kwargs):
    default_log.info(fmt, *args, **kwargs)


def warning(fmt, *args, **kwargs):
    default_log.warning(fmt, *args, **kwargs)


def warn(fmt, *args, **kwargs):
    default_log.warn(fmt, *args, **kwargs)


def error(fmt, *args, **kwargs):
    default_log.error(fmt, *args, **kwargs)


def exception(fmt, *args, **kwargs):
    error(fmt, *args, **kwargs)
    error("Except stack:%s", traceback.format_exc(), **kwargs)


def critical(fmt, *args, **kwargs):
    default_log.critical(fmt, *args, **kwargs)
