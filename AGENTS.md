# AGENTS.md

This document provides guidance for AI coding agents working on the XX-Net codebase.

## Project Overview

XX-Net is a Python 3 network proxy/VPN application that supports multiple platforms (Windows, macOS, Linux, Android, iOS). It provides proxy services through GAE (Google App Engine) and X-Tunnel modules with intelligent routing via smart_router.

## Build/Lint/Test Commands

### Running Tests

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run a single test file
pytest code/default/lib/tests/test_utils.py

# Run a single test class
pytest code/default/lib/tests/test_utils.py::TestIP

# Run a single test method
pytest code/default/lib/tests/test_utils.py::TestIP::test_check_ipv4

# Run tests with timeout (configured in pytest.ini)
pytest --timeout=200
```

### Running the Application

```bash
# Linux/macOS
./start

# Windows
start.bat

# With command line options
./start -allow_remote -no_mess_system -no_popup -no_systray
```

### Dependencies

Install required packages:
```bash
pip install -r requirements.txt
```

Main dependencies: OpenSSL, babel, jinja2, googletrans==4.0.0-rc1

## Code Style Guidelines

### Imports

Order imports in the following groups, separated by blank lines:

1. Standard library imports (alphabetical)
2. Third-party imports (alphabetical)
3. Local/application imports (alphabetical)

```python
# Standard library
import json
import os
import sys
import time
import traceback

# Third-party
import simple_http_client
import simple_http_server

# Local
from xlog import getLogger
import utils
from . import global_var as g
```

Use relative imports for submodules:
```python
from .socket_wrap import SocketWrap
from . import global_var as g
```

### File Header

Python files should start with:
```python
#!/usr/bin/env python3
# coding:utf-8
```

Or for compatibility:
```python
#!/usr/bin/env python
# coding:utf-8
```

### Naming Conventions

- **Variables**: snake_case (`server_host`, `client_address`)
- **Functions**: snake_case (`def start()`, `def get_ip_port()`)
- **Classes**: PascalCase (`class GAEProxyHandler`, `class ConnectFail`)
- **Constants**: UPPER_SNAKE_CASE (`SO_ORIGINAL_DST`, `DEFAULT_PORT`)
- **Private attributes**: Single underscore prefix (`_sock`, `_local`)
- **Module-level globals**: Use `g` module pattern (`g.config`, `g.running`)

### Error Handling

Define custom exception classes at module level:

```python
class DontFakeCA(Exception):
    pass

class ConnectFail(Exception):
    pass

class NotSupported(Exception):
    def __init__(self, req, sock):
        self.req = req
        self.sock = sock
```

Use specific exception handling:

```python
try:
    # operation
except (socket.error, ssl.SSLError) as e:
    xlog.warn("connection failed: %r", e)
except Exception as e:
    xlog.exception("unexpected error: %r", e)
```

### Logging

Use `xlog` logger throughout the codebase:

```python
from xlog import getLogger
xlog = getLogger("module_name", log_path=log_dir, save_start_log=500, save_warning_log=True)

# Log levels
xlog.debug("debug message: %s", value)
xlog.info("info message: %s", value)
xlog.warn("warning message: %s", value)
xlog.error("error message: %s", value)
xlog.exception("exception context: %r", exception_object)
```

### Configuration

Use `xconfig.Config` for configuration management:

```python
import xconfig
config = xconfig.Config(config_path)
config.set_var("key", default_value)
config.load()
value = config.key
```

### Code Patterns

#### Path Setup Pattern

Files that need access to project modules should set up paths:

```python
current_path = os.path.dirname(os.path.abspath(__file__))
default_path = os.path.abspath(os.path.join(current_path, os.pardir))
noarch_lib = os.path.abspath(os.path.join(default_path, 'lib', 'noarch'))
sys.path.append(noarch_lib)
sys.path.append(default_path)
```

#### Data Path Pattern

```python
import env_info
data_path = env_info.data_path
data_module_path = os.path.join(data_path, 'module_name')
```

#### Module Initialization

Follow the module pattern with `start()` and `stop()` functions:

```python
def start(args):
    global ready
    # initialization code
    ready = True

def stop():
    global ready
    # cleanup code
    ready = False

def is_ready():
    return ready
```

### Threading

Use daemon threads for background tasks:

```python
import threading

p = threading.Thread(target=target_func, args=(args,), name="thread_name")
p.daemon = True
p.start()
```

### Testing

Use `unittest` or `pytest`:

```python
# unittest style
import unittest

class TestSomething(unittest.TestCase):
    def test_feature(self):
        self.assertEqual(actual, expected)

# pytest style with TestCase
from unittest import TestCase

class TestSomething(TestCase):
    def setUp(self):
        self.base_url = "http://localhost:8085"

    def test_feature(self):
        self.assertTrue(condition)
```

### Type Hints

Type hints are not used consistently in the codebase. When adding new code, maintain consistency with existing patterns in the file being modified.

## Project Structure

```
XX-Net/
├── code/default/
│   ├── launcher/        # Main entry point and system integration
│   ├── gae_proxy/       # Google App Engine proxy module
│   ├── x_tunnel/        # X-Tunnel proxy module
│   ├── smart_router/    # Intelligent routing module
│   └── lib/             # Shared libraries
├── pytest.ini           # Pytest configuration
├── requirements.txt     # Python dependencies
└── start                # Linux/macOS startup script
```

## Important Notes

1. **Cross-platform compatibility**: Code must work on Windows, macOS, Linux, Android, and iOS
2. **Python 2/3 compatibility**: Some patterns support both Python versions (e.g., `try/except ImportError` for urllib imports)
3. **Resource constraints**: Thread stack size is reduced for OpenWrt/embedded systems
4. **Global state**: Use the `global_var` pattern (`g`) for shared module state
5. **Do not add comments** unless explicitly requested by the user