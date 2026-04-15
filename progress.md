## Goal

按照 `现代化重构计划.md` 对 XX-Net 项目进行 Python 代码现代化重构，涵盖 5 个阶段。

## Instructions

- 使用 `C:\WorkSpace\XX-Net\python3\python.exe` 运行所有测试和应用程序
- 重构不得改变用户可见的功能或行为
- 每次提交前需要手动测试：启动 XX-Net，运行 `curl -x socks5://127.0.0.1:1080 -I https://github.com -k` 并验证 HTTP/1.1 200 响应
- 用户要求"一站式完成，中途保持沉默，除非遇到无法解决的报错"

## Discoveries

### hyperframe 6.x API 变更 (已修复)
- `SettingsFrame.SETTINGS_MAX_FRAME_SIZE` → `SettingsFrame.MAX_FRAME_SIZE`
- `Flags` 使用字符串而非字节：`b'ACK'` → `'ACK'`
- `GoAwayFrame._extra_info()` 方法不存在 → 应使用 `frame.additional_data` 或 `frame.explain`

### ssl_wrap.recv() str/bytes bug (已修复)
- `ssl_wrap.py:187` 在异常时返回 `''` (字符串) 而不是 `b''` (字节)
- 已修复：`return ''` → `return b''`

### HTTP/2 短读取 bug (已修复)
- `_consume_single_frame()` 中 `recv(9)` 可能返回少于 9 字节
- 已修复：添加长度检查并关闭连接

### HTTPHeaderMap 初始化 bug (已修复)
- `http2_stream.py:289`: `hpack.Decoder.decode()` 返回 list of tuples
- 修复：改为 `HTTPHeaderMap(dict(headers))`

### tlslite 是死代码 (已删除)
- `tlslite_wrap.py` 在整个项目中没有任何 import 引用
- 所有 SSL 操作使用 `ssl_wrap.py`（stdlib ssl）
- 已删除 tlslite/ 目录（148 文件，~2MB）和 tlslite_wrap.py

### Phase 4 async 架构设计
- 采用"并存模式"：async 模块与同步模块并存，不修改现有同步代码
- `async_loop.py` 在后台线程运行 asyncio 事件循环
- 同步代码可通过 `run_async()` 调用异步代码，异步代码可通过 `run_sync()` 调用阻塞代码
- async_client.py 使用 socket pair + executor 桥接到 sync proxy_session

## Accomplished

### ✅ 已完成（46 个提交）

| Phase | 内容 |
|-------|------|
| **Phase 1** | 清理遗留（删除 six.py, py3_compat.py, pyopenssl_wrap.py, selectors2.py；清理 sys.version_info 分支, SSLv3/SSLv2 回退） |
| **Phase 2** | 依赖现代化（删除捆绑库 ~54,000行，改用 pip：pyasn1, dnslib, sortedcontainers, asn1crypto, ecdsa, PySocks） |
| **Phase 2.1.2** | hyper 捆绑库 → h2/hpack/hyperframe + hyper_compat shim（~17,800 行删除） |
| **Phase 3.1** | HTTP server 替换（stdlib http.server + ThreadingMixIn） |
| **Phase 3.2** | HTTP client 替换（httpx 替代手动 HTTP 客户端） |
| **Phase 3.3** | 64 处裸 `except:` → 类型化异常 |
| **Phase 3.4** | 全局状态封装为 XTunnelContext（proxy 模式保持向后兼容） |
| **Phase 3.5** | 核心模块类型注解 |
| **Phase 4** | asyncio 基础设施 + async_client.py 完成（async SOCKS5 服务器，socket pair 桥接） |
| **Phase 5.1** | CI/CD 更新（Python 3.12/3.13, Linux/Windows/macOS） |
| **Phase 5.2** | 测试覆盖率提升（base_container 27t, proxy_session 4t, connect_creator 8t, front_dispatcher 9t） |
| **Phase 5.3** | 集成测试框架（纯 Python Mock 服务器：HTTP/HTTP2/SOCKS5） |
| **Phase 5.7** | 移除 tlslite 捆绑（~2MB, 148 文件 + tlslite_wrap.py） |
| **Bug fixes** | ssl_wrap.recv(), HTTP/2 短读取, HTTPHeaderMap 初始化 |

**测试状态**：187 tests pass（184 project + 3 SOCKS5 integration），3 pre-existing DNS failures

**人工测试**：✅ `curl -x socks5://127.0.0.1:1080 https://github.com` 成功返回 HTTP/1.1 200

**删除代码统计**：~100,400 行

### 📋 待完成

| 任务 | 状态 | 风险 |
|------|------|-------|
| Phase 5.5: Web UI 现代化 | pending | 低 |

## Relevant files

### async 模块（Phase 4）
- `code/default/x_tunnel/local/async_client.py` — async 模式入口点（~434 行）
- `code/default/lib/noarch/async_loop.py` — asyncio 事件循环管理器
- `code/default/lib/noarch/async_http_server.py` — aiohttp 异步 HTTP 服务器
- `code/default/lib/noarch/async_http_client.py` — httpx 异步 HTTP 客户端
- `code/default/lib/noarch/async_socks5.py` — asyncio SOCKS5 代理
- `code/default/lib/noarch/async_ssl_wrap.py` — asyncio SSL 连接
- `code/default/lib/noarch/front_base/async_connect_creator.py` — async SSL 连接创建

### 核心同步模块
- `code/default/x_tunnel/local/client.py` — 同步入口点（153 行）
- `code/default/x_tunnel/local/__init__.py` — 模块初始化，支持 async/sync 切换
- `code/default/x_tunnel/local/proxy_session.py` — 核心协议逻辑（1420 行）
- `code/default/x_tunnel/local/base_container.py` — 数据管道（977 行）
- `code/default/x_tunnel/local/context.py` — XTunnelContext + XTunnelStat
- `code/default/x_tunnel/local/global_var.py` — 全局变量代理

### 测试文件
- `code/default/lib/tests/test_phase4_async.py` — Phase 4 异步模块测试（18 tests）
- `code/default/lib/tests/test_xtunnel_socks5.py` — SOCKS5 集成测试（3 tests）
- `code/default/lib/tests/test_base_container.py` — base_container 单元测试（27 tests）
- `code/default/lib/tests/test_proxy_session.py` — proxy_session 辅助函数测试（4 tests）
- `code/default/lib/tests/test_connect_creator.py` — connect_creator 单元测试（8 tests）
- `code/default/lib/tests/test_front_dispatcher.py` — front_dispatcher 单元测试（9 tests）

## Usage

启用 async 模式：
```bash
set XXNET_ASYNC=1
python start.bat
```

默认使用同步模式（无需任何配置更改）。