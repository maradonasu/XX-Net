#!/usr/bin/env python3
# coding:utf-8
"""
JSON-file backed configuration manager.

Provides two configuration strategies:

1. ``TypedConfig`` — dataclass-based (preferred for new code).
   Define a ``@dataclass`` with typed fields and default values,
   then wrap it with ``TypedConfig(MyConfig, path)``.

2. ``Config`` — legacy dict-based (kept for ``front_base.ConfigBase``
   subclasses).  Uses ``set_var / load / save`` API.

Both persist to the same JSON format and are backward-compatible.
"""

import json
import os
import time
import logging
from dataclasses import dataclass, fields, MISSING, field
from typing import Any, Dict, List, Optional, Type, TypeVar

_logger = logging.getLogger('config_manager')


class TypedConfig:
    """Configuration backed by a dataclass definition and a JSON file.

    Usage::

        @dataclass
        class LauncherConfig:
            host: str = "127.0.0.1"
            port: int = 8085
            tags: List[str] = field(default_factory=list)

        config = TypedConfig(LauncherConfig, "/path/to/config.json")
        config.port           # -> 8085  (or value from JSON)
        config.port = 9090
        config.save()         # only non-default values are written

    Dynamic (non-dataclass) attributes can be set freely for computed
    fields that should not be persisted (e.g. ``config.windows_ack``).

    The ``check_change`` method detects external file modifications and
    hot-reloads the dataclass fields.
    """

    def __init__(self, dataclass_cls: type, config_path: str):
        object.__setattr__(self, '_dc_cls', dataclass_cls)
        object.__setattr__(self, '_config_path', config_path)
        object.__setattr__(self, '_last_load_time', time.time())
        object.__setattr__(self, '_file_config', {})

        defaults: Dict[str, Any] = {}
        for f in fields(dataclass_cls):
            if f.default is not MISSING:
                defaults[f.name] = f.default
            elif f.default_factory is not MISSING:
                defaults[f.name] = f.default_factory()
        object.__setattr__(self, '_defaults', defaults)

        for name, val in defaults.items():
            object.__setattr__(self, name, val)

        self._load_from_file()

    def _load_from_file(self) -> None:
        object.__setattr__(self, '_last_load_time', time.time())
        path = object.__getattribute__(self, '_config_path')
        if not os.path.isfile(path):
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.strip().replace("\r", "").replace("\n", "").replace(",}", "}")
            file_config: Dict[str, Any] = json.loads(content)
        except Exception as e:
            _logger.warning("Loading config:%s fail:%r", path, e)
            return

        object.__setattr__(self, '_file_config', file_config)

        dc_cls = object.__getattribute__(self, '_dc_cls')
        for f in fields(dc_cls):
            if f.name in file_config:
                object.__setattr__(self, f.name, file_config[f.name])

    def save(self) -> None:
        path = object.__getattribute__(self, '_config_path')
        defaults = object.__getattribute__(self, '_defaults')
        dc_cls = object.__getattribute__(self, '_dc_cls')

        file_config: Dict[str, Any] = {}
        for f in fields(dc_cls):
            val = object.__getattribute__(self, f.name)
            if f.name in defaults and val == defaults[f.name]:
                continue
            file_config[f.name] = val

        with open(path, "w", encoding='utf-8') as f:
            f.write(json.dumps(file_config, indent=2, ensure_ascii=False))

    def load(self) -> None:
        self._load_from_file()

    @property
    def default_config(self) -> Dict[str, Any]:
        return dict(object.__getattribute__(self, '_defaults'))

    def check_change(self) -> None:
        path = object.__getattribute__(self, '_config_path')
        last = object.__getattribute__(self, '_last_load_time')
        try:
            if os.path.getmtime(path) > last:
                self._load_from_file()
                _logger.info("reload config %s", path)
        except OSError:
            pass

    def __repr__(self) -> str:
        dc_cls = object.__getattribute__(self, '_dc_cls')
        path = object.__getattribute__(self, '_config_path')
        return f"TypedConfig({dc_cls.__name__}, {path!r})"


class Config:
    """Legacy dict-based configuration (kept for front_base.ConfigBase).

    Prefer ``TypedConfig`` for new code.
    """

    def __init__(self, config_path):
        self.last_load_time = time.time()
        self.default_config: Dict[str, Any] = {}
        self.file_config: Dict[str, Any] = {}
        self.config_path = config_path
        self.set_default()

    def set_default(self):
        pass

    def check_change(self):
        try:
            if os.path.getmtime(self.config_path) > self.last_load_time:
                self.load()
                _logger.info("reload config %s", self.config_path)
        except OSError:
            pass

    def load(self):
        self.last_load_time = time.time()
        if os.path.isfile(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                content = content.strip()
                content = content.replace("\r", "")
                content = content.replace("\n", "")
                content = content.replace(",}", "}")
                try:
                    self.file_config = json.loads(content)
                except Exception as e:
                    _logger.warning("Loading config:%s content:%s fail:%r", self.config_path, content, e)
                    self.file_config = {}

        for var_name in self.default_config:
            if self.file_config and var_name in self.file_config:
                setattr(self, var_name, self.file_config[var_name])
            else:
                setattr(self, var_name, self.default_config[var_name])

    def save(self):
        for var_name in self.default_config:
            if getattr(self, var_name, None) == self.default_config[var_name]:
                if var_name in self.file_config:
                    del self.file_config[var_name]
            else:
                self.file_config[var_name] = getattr(self, var_name)

        with open(self.config_path, "w", encoding='utf-8') as f:
            f.write(json.dumps(self.file_config, indent=2, ensure_ascii=False))

    def set_var(self, var_name, default_value):
        self.default_config[var_name] = default_value
