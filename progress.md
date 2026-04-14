## Goal

对 XX-Net 项目进行 Python 代码现代化重构，按照 `现代化重构计划.md` 中的 5 个阶段执行。

## Instructions

- 使用项目中 `python3/python.exe` 的嵌入式 Python 运行所有测试
- 重构不改变用户可见功能和行为
- 提交前需人工测试验证，检查日志确认无问题
- 用户要求"一站式完成，中途保持沉默，除非遇到无法解决的报错"

## Discoveries

### Socket handoff issue（已解决）
- **根因**：HTTPServer 的 `process_request_thread` 在 handler 返回后直接调用 `request.close()`，但 SOCKS5 handler 已将 socket 交给 `Conn` 对象
- **修复**：添加 `handoff_socket` 标志，`finish()` 方法检查此标志后才关闭 socket

### Selector 竞态条件（已解决）
- **问题**：`_find_and_remove_bad_fd` 用 `getsockopt(SO_ERROR)` 检测坏 fd，但在 Windows 上可能误杀正常 socket
- **修复**：简化逻辑，只检查 `fileno() < 0`

### Non-blocking socket（已解决）
- **问题**：`do_connect` 创建 socket 后使用 blocking 模式 + timeout，导致 selector 行为不一致
- **修复**：connect 成功后立即调用 `sock.setblocking(False)`

## Accomplished

### ✅ 已完成（23 个提交）

| Commit | 内容 |
|--------|------|
| `e2dc1faf` | Phase 1: 清理遗留（删除 six.py, py3_compat.py, pyopenssl_wrap.py, selectors2.py） |
| `43700661` | Phase 2: 依赖现代化（删除捆绑库 ~54,000行，改用 pip） |
| `a99d579d` | Phase 3.3: 64 处裸 `except:` → 类型化异常 |
| `1df12601` | Phase 3 partial: 类型注解 + boringssl fix |
| `d3ad42da` | Startup bug fixes |
| `625e0751` | Phase 3.5: base_container 类型注解 + CI |
| `30702d8b` | Phase 3.5: connect_manager 类型注解 |
| `93f16da1` | Phase 3.5: proxy_handler/proxy_session 类型注解 |
| `321d4b15` | Phase 3.4/3.5: XTunnelContext 类 + front_dispatcher/connect_creator 类型注解 |
| `ba032d16` | 添加 httpx 到 requirements.txt |
| `19c5d8d2` | Phase 3.1: HTTP server 替换 |
| `214b1363` | HTTPServer 添加 init_socket/serve_forever |
| `1c8c38d5` | WinError 10038 处理 |
| `b97eeed5` | _SelectorWrapper.select() 处理 stale fd |
| `d1a6c5cd` | 逐个 fd 探测清除坏 fd |
| `3a42b3f1` | 保守 fd 检查避免误杀 |
| `cdcf3b7f` | 隔离坏 fd：unregister/test/re-register |
| `03313055` | add_sock_event 前检查 fileno() |
| `1cddd021` | recv BlockingIOError 不关闭连接 |
| `4cb2a11e` | Fix selector race: use getsockopt, set non-blocking |
| `789054b4` | Fix socket handoff: HTTPServer must not close handed-off sockets |

**测试状态**：84 tests pass, 3 pre-existing DNS failures

**人工测试**：✅ `curl -x socks5://127.0.0.1:1080 https://github.com` 成功返回 HTTP/1.1 200

### 📋 待完成

| 任务 | 状态 | 风险 |
|------|------|-------|
| Phase 3.2: HTTP client 替换 | pending | 中 |
| Phase 4: asyncio 改造 | pending | 高 |

## Relevant files

### 核心修复文件
- `code/default/lib/noarch/http_server.py` — HTTPServer with handoff_socket flag
- `code/default/x_tunnel/local/proxy_handler.py` — Socks5Server with finish() method
- `code/default/x_tunnel/local/base_container.py` — _SelectorWrapper, do_connect fixes

### 下一步
Phase 3.1 HTTP server 替换已完成并通过人工测试。可以继续 Phase 3.2 HTTP client 替换。