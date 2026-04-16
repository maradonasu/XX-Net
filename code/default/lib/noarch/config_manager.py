#!/usr/bin/env python3
# coding:utf-8
"""
JSON-file backed configuration manager.

Replaces the former xconfig.py.  Uses stdlib logging.
Maintains the same ``set_var / load / save`` API for backward compatibility.
"""

import json
import os
import time
import logging

_logger = logging.getLogger('config_manager')


class Config:
    def __init__(self, config_path):
        self.last_load_time = time.time()
        self.default_config = {}
        self.file_config = {}
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
