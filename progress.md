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

### hyper 替换（已解决）
- **根因**：hyper 0.5.0 捆绑库已废弃，需要用 h2/hpack/hyperframe 替代
- **方案**：创建 `hyper_compat` shim 模块，提供 hyper 兼容接口，底层使用 pip 包

### Hyperframe 6.x breaking changes（已解决）
- `SettingsFrame.SETTINGS_MAX_FRAME_SIZE` → `SettingsFrame.MAX_FRAME_SIZE`
- `Flags` 使用字符串而非字节：`b'ACK'` → `'ACK'`

### HTTP client 替换（已解决）
- `simple_http_client.py` 高层 `Client`/`request()` 用 httpx 替换
- 底层 `BaseResponse`/`Response`/`Connection` 保留用于 socket 级解析

### HTTP/2 运行时 bug（已解决）
- **ssl_wrap.recv() str/bytes**：Line 187 异常时返回 `''` 而非 `b''`，导致 `struct.unpack()` 失败
- **HTTP/2 短读取**：`recv(9)` 可能返回少于 9 字节，导致 `InvalidFrameError`
- **HTTPHeaderMap 初始化**：`hpack.Decoder.decode()` 返回 list of tuples，`HTTPHeaderMap(headers)` 错误构造字典

### global_var 封装（已解决）
- **方案**：`global_var.py` 用 `_GlobalVarProxy` 替换模块自身（`sys.modules` 替换），所有属性委托到 `XTunnelContext` 单例
- `XTunnelStat` 支持 `__getitem__`/`__setitem__` 保持 `g.stat["key"]` 向后兼容
- 所有 7 个消费模块无需修改，`from . import global_var as g` 继续正常工作

## Accomplished

### ✅ 已完成（40 个提交）

| Phase | 内容 |
|-------|------|
| **Phase 1** | 清理遗留（删除 six.py, py3_compat.py, pyopenssl_wrap.py, selectors2.py；清理 sys.version_info 分支, SSLv3/SSLv2 回退） |
| **Phase 2** | 依赖现代化（删除捆绑库 ~54,000行，改用 pip：pyasn1, dnslib, sortedcontainers, asn1crypto, ecdsa, PySocks） |
| **Phase 2.1.2** | hyper 捆绑库 → h2/hpack/hyperframe + hyper_compat shim（~17,800 行删除） |
| **Phase 3.1** | HTTP server 替换（stdlib http.server + ThreadingMixIn） |
| **Phase 3.2** | HTTP client 替换（httpx 替代手动 HTTP 客户端） |
| **Phase 3.3** | 64 处裸 `except:` → 类型化异常 |
| **Phase 3.4** | 全局状态封装为 XTunnelContext（proxy 模式保持向后兼容） |
| **Phase 3.5** | 核心模块类型注解（utils, base_container, connect_manager, connect_creator, front_dispatcher, proxy_handler, proxy_session, context） |
| **Phase 5.1** | CI/CD 更新（Python 3.12/3.13, Linux/Windows/macOS） |
| **Bug fixes** | ssl_wrap.recv(), HTTP/2 短读取, HTTPHeaderMap 初始化 |

**测试状态**：93 tests pass, 3 pre-existing DNS failures

**人工测试**：✅ `curl -x socks5://127.0.0.1:1080 https://github.com` 成功返回 HTTP/1.1 200

**删除代码统计**：
- Phase 1: ~1,500 行
- Phase 2: ~54,000 行
- Phase 2.1.2: ~17,800 行
- Phase 3.2: ~91 行（净减少）
- **总计删除：~73,400 行**

### 📋 待完成

| 任务 | 状态 | 风险 |
|------|------|-------|
| Phase 4: asyncio 改造 | pending（可选） | 高 |
| Phase 5.2: 测试覆盖率提升 | pending | 低 |
| Phase 5.3: 集成测试框架 | pending | 中 |
| Phase 5.5: Web UI 现代化 | pending | 低 |
| Phase 5.7: 移除 tlslite 捆绑 | pending | 低 |

## Relevant files

### 新增/关键文件
- `code/default/lib/noarch/hyper_compat/__init__.py` — hyper shim（~460 行）
- `code/default/x_tunnel/local/context.py` — XTunnelContext + XTunnelStat
- `code/default/x_tunnel/local/global_var.py` — _GlobalVarProxy 委托到 XTunnelContext
- `.github/workflows/ci.yml` — CI/CD 配置
