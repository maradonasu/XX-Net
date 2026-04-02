# XX-Net .NET 10 + C# + WinUI 3 Windows 11 重构计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前以 Python 为主的 `launcher + x_tunnel + 自带网络/TLS/HTTP2 基础库` 重构为仅运行于 Windows 11 的 `.NET 10 + C# + WinUI 3` 桌面应用与后台服务体系，提升可维护性、可诊断性、Windows 集成度与长期稳定性。

**Architecture:** 采用“前后台分离”的双进程架构。前台使用 `WinUI 3` 提供控制台、托盘、状态页与诊断界面；后台使用 `.NET Generic Host` 提供连接调度、代理监听、配置、日志、证书与系统代理接管等核心能力。协议与调度层优先抽象成独立类库，避免 UI 与网络核心耦合。

**Tech Stack:** `.NET 10`, `C# 13`, `WinUI 3`, `Windows App SDK`, `Microsoft.Extensions.Hosting`, `Microsoft.Extensions.DependencyInjection`, `System.Net.Sockets`, `SocketsHttpHandler`, `System.Threading.Channels`, `EventSource/EventPipe`, `MSIX` 或自包含发布。

---

## 1. 文档目的

本计划用于指导 XX-Net 在当前仓库基础上，完成一次面向 Windows 11 的产品级重构，而不是语法级移植。

本计划默认以下前提成立：

- 目标系统限定为 `Windows 11`
- 运行时限定为 `.NET 10`
- UI 技术栈限定为 `WinUI 3`
- 不再维护 macOS、Linux、Android、iOS 兼容层
- 以当前仓库的实际启用模块为准，即重点重构 `launcher + x_tunnel + win32 集成 + front_base`

## 2. 当前系统基线

根据仓库现状，当前可见结构重点如下：

- 启动入口在 `code/default/launcher/start.py`
- 模块编排在 `code/default/launcher/module_init.py`
- 当前默认启用模块主要是 `x_tunnel`
- Windows 托盘入口在 `code/default/launcher/win_tray.py`
- Windows 系统代理接管在 `code/default/lib/win32/win32_proxy_manager.py`
- 连接池、调度、HTTP/2、TLS 封装集中在 `code/default/lib/noarch/front_base/`
- 本地代理监听与 SOCKS/HTTP 处理集中在 `code/default/x_tunnel/local/`

当前系统的主要问题不是“Python 不可用”，而是：

- 跨平台兼容代码长期侵入主流程
- 线程、队列、超时、重试、连接保活分散在多层实现中
- TLS/HTTP2/连接调度使用大量自维护逻辑，理解与验证成本高
- UI、系统集成、后台运行、日志诊断没有清晰边界
- Windows 原生集成能力不足，产品化程度有限

## 3. 重构目标

### 3.1 业务目标

- 保留现有核心代理能力
- 保留本地 HTTP/SOCKS 代理入口
- 保留 X-Tunnel 相关配置、连接、会话与转发行为
- 保留 Windows 系统代理启停能力
- 保留日志、诊断、升级、配置与状态查看能力

### 3.2 工程目标

- 建立可维护的模块边界
- 建立统一的异步并发模型
- 建立统一的取消、超时、重试、熔断与恢复策略
- 建立统一的配置、日志、指标、故障转储与诊断链路
- 将 Windows 11 集成从“脚本式能力”升级为“产品级能力”

### 3.3 非目标

- 不追求与 Python 版本逐行等价
- 不优先保留历史上未启用的模块与遗留分支
- 不在第一阶段支持非 Windows 11
- 不在第一阶段支持插件化外部脚本扩展

## 4. 目标架构

## 4.1 进程划分

### 进程 A：`XXNet.Desktop`

职责：

- WinUI 3 主窗口
- 托盘菜单与通知
- 配置编辑
- 状态展示
- 日志查看
- 诊断入口
- 版本更新入口
- 与后台服务的本机 IPC

### 进程 B：`XXNet.ServiceHost`

职责：

- 本地 HTTP/SOCKS 代理监听
- X-Tunnel 会话管理
- 连接池与连接调度
- 远端 front 选择与健康检查
- 配置持久化
- 证书与系统代理接管
- 后台保活
- 结构化日志与指标输出

### 可选进程 C：`XXNet.Updater`

职责：

- 安装、升级、回滚
- 文件替换
- 自更新保护
- 管理员权限操作隔离

建议将升级器独立，以避免主进程自更新时锁文件。

## 4.2 解决方案结构

建议新建如下 Solution：

```text
src/
  XXNet.Desktop/
  XXNet.ServiceHost/
  XXNet.Core/
  XXNet.Proxy/
  XXNet.XTunnel/
  XXNet.Transport/
  XXNet.Windows/
  XXNet.Contracts/
  XXNet.Diagnostics/
  XXNet.Updater/
tests/
  XXNet.Core.Tests/
  XXNet.Proxy.Tests/
  XXNet.XTunnel.Tests/
  XXNet.Transport.Tests/
  XXNet.Windows.Tests/
  XXNet.Integration.Tests/
  XXNet.Perf.Tests/
```

各项目职责：

- `XXNet.Desktop`
  WinUI 3 桌面前端与 ViewModel 绑定层
- `XXNet.ServiceHost`
  Generic Host 后台宿主与生命周期管理
- `XXNet.Core`
  配置、模型、错误码、时间、通用策略
- `XXNet.Proxy`
  HTTP/SOCKS 入站代理协议解析与监听
- `XXNet.XTunnel`
  会话、连接、分片、收发、ACK、重试、调度策略
- `XXNet.Transport`
  TLS、HTTP/1.1、HTTP/2、连接池、front 连接抽象
- `XXNet.Windows`
  系统代理、证书、托盘、单实例、注册表、Windows 集成
- `XXNet.Contracts`
  UI 与后台 IPC 合同、DTO、命令与事件
- `XXNet.Diagnostics`
  日志、事件、指标、导出、故障包
- `XXNet.Updater`
  独立升级器

## 4.3 通信模型

桌面端与后台端建议通过本地 IPC 通信，不走 HTTP Web 控制台模式。

建议方案：

- 首选：`Named Pipes`
- 备选：本机环回 `gRPC over Unix Domain Socket for Windows equivalent is limited`, 因此不作为首选

建议通信内容：

- 获取状态快照
- 订阅实时状态流
- 修改配置
- 启停代理
- 触发连接重置
- 导出日志与诊断包
- 执行升级/回滚

## 5. 核心技术决策

## 5.1 UI 技术

采用 `WinUI 3 + Windows App SDK`。

原因：

- 符合 Windows 11 桌面应用方向
- 原生支持现代窗口、通知、主题、设置体验
- 与 Windows 11 视觉与系统能力集成更自然
- 比 Web 控制台方案更适合“只做 Windows 11 产品”

注意事项：

- 托盘能力需要通过 Win32 互操作补齐
- 单实例、窗口唤起、管理员权限、开机启动需要额外封装

## 5.2 后台宿主

采用 `.NET Generic Host`。

原因：

- 统一后台生命周期
- 统一依赖注入
- 统一配置源
- 统一日志、指标、HostedService 管理
- 方便拆成控制台模式、后台模式、服务模式

## 5.3 网络并发模型

采用“异步 IO + `Channel<T>` + 有界队列 + 后台 Worker”的并发模型。

禁止直接按 Python 版本的“每层一个 Thread + Queue + select”结构翻译。

原因：

- 更易实现统一取消
- 更易做背压控制
- 更易做高并发诊断
- 更适合长期运行

## 5.4 TLS 与 HTTP/2

目标分为两层：

- 第一层：基于 .NET 内建 `SslStream`、`SocketsHttpHandler`、HTTP/2 能力优先落地
- 第二层：针对与现网兼容性差异，再补专用 Transport 适配层

关键原则：

- 先验证“内建栈是否足以覆盖主要场景”
- 不要在项目第一阶段自建整套 TLS 栈
- 只有当现网成功率、握手行为、ALPN、连接复用无法满足时，才进入定制 Transport

## 5.5 部署方式

部署策略分两档：

- 开发阶段：自包含发布，便于快速分发
- 正式阶段：优先评估 `MSIX` 或受控自包含安装器

如果采用 Windows App SDK 非打包模式，需要在启动时正确处理运行时初始化与依赖引导。

## 5.6 可观测性

必须从第一天设计进去：

- 结构化日志
- 会话级关联 ID
- 连接级关联 ID
- EventSource 事件
- 指标采样
- 性能快照导出
- 崩溃转储采集

## 6. 重构策略

本项目不建议“一次性替换上线”。

建议采用四阶段策略：

### 阶段 0：基线测量

先测清当前版本的：

- 启动耗时
- 代理监听建立耗时
- 系统代理切换耗时
- 首个可用连接耗时
- 常见站点请求成功率
- 长连稳定性
- CPU 占用
- 内存占用
- 日志完整性
- 异常恢复能力

没有基线，就无法证明重构收益。

### 阶段 1：壳层重写

优先重写：

- 启动器
- WinUI 3 桌面 UI
- 托盘
- 配置系统
- 日志系统
- Windows 代理接管
- 后台宿主

这一阶段可以先让后台核心仍调用旧实现或只打通最小链路。

### 阶段 2：代理入口与会话重写

重写：

- 本地 HTTP 代理
- 本地 SOCKS5 代理
- 基础会话模型
- 入站连接状态机
- 配置热加载
- 基础诊断链路

### 阶段 3：X-Tunnel 与 Transport 重写

重写：

- X-Tunnel 会话与调度
- front 选择策略
- 连接池
- 重试与保活
- TLS/HTTP2 传输抽象

### 阶段 4：升级、回滚、硬化与替换上线

完成：

- 升级器
- 迁移工具
- 回滚能力
- 稳定性测试
- 打包与签名
- 灰度替换

## 7. 模块拆解计划

## 7.1 `launcher` 重构为 `XXNet.Desktop + XXNet.ServiceHost`

现有能力映射：

- `start.py` -> `Program.cs` + Host 启动入口
- `module_init.py` -> 模块编排服务
- `web_control.py` -> IPC 控制面 + WinUI 页面
- `win_tray.py` -> 托盘服务
- `config.py` -> `Options + JSON 配置 + 配置仓储`

输出目标：

- 移除浏览器 Web 控制台作为主控制入口
- 移除 Python 启动脚本依赖
- 将模块生命周期统一收口到 Host

## 7.2 `win32_proxy_manager` 重构为 `XXNet.Windows.Proxy`

重写内容：

- 系统代理启停
- 当前代理状态查询
- 异常恢复
- 与 UI 的状态同步

增加能力：

- 失败回滚
- 启停幂等
- 与进程退出的清理钩子
- 代理接管冲突提示

## 7.3 `x_tunnel/local/proxy_handler.py` 重构为 `XXNet.Proxy`

重写内容：

- SOCKS4/4a/5 协议解析
- HTTP CONNECT
- HTTP 正向代理
- 入站超时控制
- 连接取消

设计原则：

- 一个入站连接一个状态对象
- 一个状态对象只管理自身缓冲与生命周期
- 读写循环必须支持 `CancellationToken`
- 不允许隐式阻塞等待

## 7.4 `front_base` 重构为 `XXNet.Transport`

重写内容：

- 连接池
- worker 调度
- HTTP/1.1 worker
- HTTP/2 worker
- front 健康检测
- keep-alive
- RTT 与吞吐统计

设计原则：

- Transport 只处理传输，不理解 UI
- 与 X-Tunnel 间只暴露接口和结果对象
- 指标必须内置
- 任何连接关闭都必须带原因码

## 7.5 `proxy_session.py + front_dispatcher.py + base_container.py` 重构为 `XXNet.XTunnel`

重写内容：

- 会话建立
- 连接 ID 管理
- 分片发送
- ACK 与重试
- 上下行流控
- front 评分
- 失败惩罚与衰减

建议拆分子模块：

- `SessionCoordinator`
- `TunnelConnectionRegistry`
- `OutboundFrameWriter`
- `InboundFrameAssembler`
- `AckTracker`
- `FrontSelector`
- `HealthSnapshotProvider`

## 7.6 `web_control` 重构为 WinUI 页面 + IPC API

页面建议：

- Dashboard
- Proxy Status
- Tunnel Status
- Connections
- Logs
- Diagnostics
- Settings
- Update

IPC 命令建议：

- `GetAppStatus`
- `GetConnectionStats`
- `GetActiveSessions`
- `EnableSystemProxy`
- `DisableSystemProxy`
- `RestartTunnel`
- `ReloadConfig`
- `ExportDiagnostics`
- `CheckForUpdate`

## 8. 分阶段实施计划

### Task 1: 基线冻结与需求收口

**Files:**
- Create: `NET10_WINUI3_WIN11_REFACTOR_PLAN.md`
- Create: `migration/baseline/current-feature-matrix.md`
- Create: `migration/baseline/current-performance-baseline.md`
- Create: `migration/baseline/current-config-schema.md`

- [ ] **Step 1: 盘点现有功能矩阵**

输出以下内容：

- 启动参数
- 配置项
- 托盘动作
- 系统代理动作
- 本地监听端口
- 代理协议
- X-Tunnel 功能
- 更新功能
- 日志与诊断功能

- [ ] **Step 2: 建立基线性能数据**

至少覆盖：

- 冷启动到监听完成耗时
- 开启系统代理耗时
- 10 分钟空闲内存
- 10 分钟活动内存
- 100/500 并发连接 CPU
- 首包延迟
- 连接成功率

- [ ] **Step 3: 冻结首版必做范围**

首版必须覆盖：

- WinUI 桌面壳
- 托盘
- 后台宿主
- 系统代理启停
- HTTP/SOCKS 入站
- X-Tunnel 基础链路

### Task 2: 建立新 Solution 与工程骨架

**Files:**
- Create: `src/XXNet.Desktop/XXNet.Desktop.csproj`
- Create: `src/XXNet.ServiceHost/XXNet.ServiceHost.csproj`
- Create: `src/XXNet.Core/XXNet.Core.csproj`
- Create: `src/XXNet.Proxy/XXNet.Proxy.csproj`
- Create: `src/XXNet.XTunnel/XXNet.XTunnel.csproj`
- Create: `src/XXNet.Transport/XXNet.Transport.csproj`
- Create: `src/XXNet.Windows/XXNet.Windows.csproj`
- Create: `src/XXNet.Contracts/XXNet.Contracts.csproj`
- Create: `src/XXNet.Diagnostics/XXNet.Diagnostics.csproj`
- Create: `src/XXNet.Updater/XXNet.Updater.csproj`
- Create: `XXNet.Net10.sln`

- [ ] **Step 1: 初始化 Solution**
- [ ] **Step 2: 建立项目引用关系**
- [ ] **Step 3: 配置统一代码规范、分析器、警告级别与发布属性**
- [ ] **Step 4: 配置测试工程骨架**

### Task 3: Desktop 壳层与 Host 打通

**Files:**
- Create: `src/XXNet.Desktop/App.xaml`
- Create: `src/XXNet.Desktop/App.xaml.cs`
- Create: `src/XXNet.Desktop/MainWindow.xaml`
- Create: `src/XXNet.Desktop/ViewModels/MainShellViewModel.cs`
- Create: `src/XXNet.ServiceHost/Program.cs`
- Create: `src/XXNet.ServiceHost/HostedServices/AppRuntimeHostedService.cs`
- Create: `src/XXNet.Contracts/IControlChannel.cs`

- [ ] **Step 1: WinUI 3 应用启动与单实例收口**
- [ ] **Step 2: 后台 Host 启动与停止打通**
- [ ] **Step 3: Desktop 通过 Named Pipes 获取状态**
- [ ] **Step 4: 实现基础状态页**

### Task 4: 配置、日志、诊断基础设施

**Files:**
- Create: `src/XXNet.Core/Configuration/AppOptions.cs`
- Create: `src/XXNet.Core/Configuration/ConfigRepository.cs`
- Create: `src/XXNet.Diagnostics/Logging/LoggerSetup.cs`
- Create: `src/XXNet.Diagnostics/Telemetry/AppEventSource.cs`
- Create: `src/XXNet.Diagnostics/Diagnostics/DiagnosticsBundleService.cs`

- [ ] **Step 1: 定义配置模型与默认值**
- [ ] **Step 2: 实现 JSON 配置读写与版本迁移**
- [ ] **Step 3: 接入结构化日志**
- [ ] **Step 4: 接入 EventSource 与关键指标**
- [ ] **Step 5: 支持导出诊断包**

### Task 5: Windows 11 专属集成

**Files:**
- Create: `src/XXNet.Windows/Proxy/SystemProxyService.cs`
- Create: `src/XXNet.Windows/Tray/TrayIconService.cs`
- Create: `src/XXNet.Windows/Startup/StartupRegistrationService.cs`
- Create: `src/XXNet.Windows/Security/CertificateService.cs`
- Create: `src/XXNet.Windows/Instance/SingleInstanceService.cs`

- [ ] **Step 1: 实现系统代理启停与状态查询**
- [ ] **Step 2: 实现托盘菜单与状态同步**
- [ ] **Step 3: 实现开机启动注册**
- [ ] **Step 4: 实现证书安装与卸载**
- [ ] **Step 5: 实现异常退出清理**

### Task 6: 本地代理入口

**Files:**
- Create: `src/XXNet.Proxy/Listeners/ProxyListenerService.cs`
- Create: `src/XXNet.Proxy/Socks/SocksConnectionHandler.cs`
- Create: `src/XXNet.Proxy/Http/HttpProxyConnectionHandler.cs`
- Create: `src/XXNet.Proxy/Common/ConnectionContext.cs`
- Create: `tests/XXNet.Proxy.Tests/SocksConnectionHandlerTests.cs`
- Create: `tests/XXNet.Proxy.Tests/HttpProxyConnectionHandlerTests.cs`

- [ ] **Step 1: 先写 SOCKS4/5 解析测试**
- [ ] **Step 2: 再实现 SOCKS4/5**
- [ ] **Step 3: 写 HTTP CONNECT 与普通代理测试**
- [ ] **Step 4: 实现 HTTP 代理入口**
- [ ] **Step 5: 加入超时、取消、异常关闭测试**

### Task 7: X-Tunnel 会话核心

**Files:**
- Create: `src/XXNet.XTunnel/Sessions/SessionCoordinator.cs`
- Create: `src/XXNet.XTunnel/Sessions/TunnelConnectionRegistry.cs`
- Create: `src/XXNet.XTunnel/Flow/AckTracker.cs`
- Create: `src/XXNet.XTunnel/Flow/OutboundFrameWriter.cs`
- Create: `src/XXNet.XTunnel/Flow/InboundFrameAssembler.cs`
- Create: `tests/XXNet.XTunnel.Tests/SessionCoordinatorTests.cs`

- [ ] **Step 1: 基于现网行为定义消息模型**
- [ ] **Step 2: 先写会话建立与关闭测试**
- [ ] **Step 3: 实现连接注册与生命周期**
- [ ] **Step 4: 实现 ACK/重试/超时**
- [ ] **Step 5: 实现连接状态快照**

### Task 8: Transport 重构

**Files:**
- Create: `src/XXNet.Transport/Connections/TransportConnectionPool.cs`
- Create: `src/XXNet.Transport/Dispatch/FrontSelector.cs`
- Create: `src/XXNet.Transport/Dispatch/WorkerScheduler.cs`
- Create: `src/XXNet.Transport/Protocols/Http1Transport.cs`
- Create: `src/XXNet.Transport/Protocols/Http2Transport.cs`
- Create: `tests/XXNet.Transport.Tests/FrontSelectorTests.cs`
- Create: `tests/XXNet.Transport.Tests/TransportConnectionPoolTests.cs`

- [ ] **Step 1: 先写连接池和 front 评分测试**
- [ ] **Step 2: 实现连接池**
- [ ] **Step 3: 实现 front 评分与衰减**
- [ ] **Step 4: 实现 worker 调度**
- [ ] **Step 5: 引入 keep-alive、RTT、吞吐统计**

### Task 9: UI 完整化

**Files:**
- Create: `src/XXNet.Desktop/Views/DashboardPage.xaml`
- Create: `src/XXNet.Desktop/Views/SettingsPage.xaml`
- Create: `src/XXNet.Desktop/Views/ConnectionsPage.xaml`
- Create: `src/XXNet.Desktop/Views/LogsPage.xaml`
- Create: `src/XXNet.Desktop/Views/DiagnosticsPage.xaml`

- [ ] **Step 1: 状态页**
- [ ] **Step 2: 设置页**
- [ ] **Step 3: 连接页**
- [ ] **Step 4: 日志页**
- [ ] **Step 5: 诊断页**

### Task 10: 升级、安装、回滚

**Files:**
- Create: `src/XXNet.Updater/Program.cs`
- Create: `src/XXNet.Updater/UpdateOrchestrator.cs`
- Create: `deployment/msix/`
- Create: `deployment/installer/`

- [ ] **Step 1: 定义安装布局**
- [ ] **Step 2: 定义升级协议**
- [ ] **Step 3: 定义失败回滚**
- [ ] **Step 4: 打通静默升级与手动升级**

## 9. 测试计划

## 9.1 测试层级

必须覆盖四层：

- 单元测试
- 协议测试
- 集成测试
- 长稳与性能测试

## 9.2 关键测试矩阵

### 代理协议

- SOCKS4
- SOCKS4a
- SOCKS5 无认证
- HTTP CONNECT
- HTTP 正向代理
- IPv4
- IPv6
- 域名目标

### 生命周期

- 首次启动
- 重启后台
- 开启系统代理
- 关闭系统代理
- UI 退出但后台继续
- 后台异常退出
- 升级后重启

### 并发与稳定性

- 100 并发短连接
- 500 并发短连接
- 长连接 30 分钟
- 空闲保活 30 分钟
- 网络波动后恢复
- 远端 front 切换

### 异常与恢复

- 配置文件损坏
- 端口被占用
- 系统代理已被其他软件接管
- 证书安装失败
- 后台进程失联
- 升级中断

## 9.3 性能验收指标

建议目标值：

- 冷启动到 UI 可用 < 2 秒
- 冷启动到后台监听可用 < 3 秒
- 系统代理启停 < 500 毫秒
- 空闲内存下降 20% 以上
- 中高并发 CPU 占用下降 15% 以上
- 相同网络环境下首包延迟不劣化超过 10%
- 24 小时长稳测试无未恢复死锁

## 10. 发布与迁移

## 10.1 配置迁移

需要提供从旧配置到新配置的迁移器：

- 读取旧版 JSON
- 映射字段
- 丢弃废弃字段
- 记录迁移日志

## 10.2 用户升级路径

建议分三段：

- 内部灰度
- 小流量外部灰度
- 全量替换

每一阶段都必须可回滚到旧版本。

## 10.3 回滚策略

必须保证：

- 配置可逆迁移或自动备份
- 安装目录保留上一版
- 升级失败可恢复旧可执行文件
- 代理设置失败时自动恢复为关闭状态

## 11. 风险清单

### 高风险

- .NET 内建 TLS/HTTP2 行为与现网兼容性不完全一致
- WinUI 3 托盘能力依赖 Win32 互操作
- 自更新与文件替换流程复杂
- Python 版隐藏行为较多，存在“看不见的业务规则”

### 中风险

- 配置迁移遗漏字段
- 旧版日志语义与新版不一致
- 部分极端网络环境下行为变化

### 低风险

- Windows 11 专属后，跨平台分支清理本身
- UI 体验升级
- 配置系统统一

## 12. 人力与周期评估

建议最小团队：

- 架构/后端负责人 1 人
- Windows 桌面开发 1 人
- 网络/协议开发 1-2 人
- 测试与发布工程 1 人

建议工期：

- 阶段 0：2 周
- 阶段 1：4 周
- 阶段 2：4-6 周
- 阶段 3：8-12 周
- 阶段 4：4 周

总计建议：`22-28 周`

如果只做“第一版可用 + 核心链路 + 基础 UI + 基础升级”，压缩后可尝试 `14-18 周`，但风险会上升。

## 13. 建议的里程碑

- M1：新 Solution 建立，Desktop + Host + IPC 可运行
- M2：系统代理、托盘、配置、日志完成
- M3：HTTP/SOCKS 代理入口完成
- M4：X-Tunnel 基础会话打通
- M5：Transport 与 front 调度完成
- M6：24 小时稳定性测试通过
- M7：升级器、迁移、回滚完成
- M8：灰度上线

## 14. 首版实施建议

如果需要控制风险，建议首版按以下优先级做：

### P0

- Desktop + Host
- 系统代理
- 托盘
- 配置
- 日志
- HTTP/SOCKS 入站
- X-Tunnel 最小可用链路

### P1

- 连接页
- 诊断页
- 自动升级
- 证书管理
- 高级 front 调度

### P2

- 更细粒度指标
- 性能调优
- 更复杂的传输策略

## 15. 官方技术边界与落地约束

本计划依赖以下官方能力边界：

- `.NET 10` 已于 `2025-11-11` 发布，属于长期支持版本，适合作为重构基线
- Windows App SDK / WinUI 3 可用于 Windows 桌面应用
- 非打包模式下需要正确处理 Windows App SDK Runtime 引导
- `.NET` 可使用 Generic Host、Windows Service、EventPipe、Native AOT 等能力，但 `WinUI 3` 主应用不建议一开始就追求 AOT，建议先以可诊断、可调试优先

## 16. 推荐实施顺序

建议严格按以下顺序推进：

1. 基线测量
2. 新 Solution 骨架
3. WinUI Desktop + 后台 Host + IPC
4. 系统代理/托盘/配置/日志
5. 入站 HTTP/SOCKS
6. X-Tunnel 会话
7. Transport 与 front 调度
8. 升级/回滚
9. 稳定性、性能、灰度

## 17. 完成定义

只有满足以下条件，才可视为重构完成：

- Windows 11 下完整安装、运行、升级、卸载闭环成立
- 用户无需 Python 环境
- UI 可替代旧 Web 控制台
- 系统代理启停可靠
- X-Tunnel 核心链路可用
- 24 小时长稳通过
- 关键性能指标达到验收值
- 可回滚

## 18. 下一步建议

建议立刻启动以下三件事：

1. 编写旧版功能矩阵与基线性能报告
2. 新建 `XXNet.Net10.sln` 与项目骨架
3. 先打通 `WinUI 3 + Generic Host + Named Pipes + 系统代理切换`

完成这三件事后，再决定是否继续深入重写 `X-Tunnel + Transport` 核心。
