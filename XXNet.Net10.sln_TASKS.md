# XXNet.Net10.sln 可执行任务清单

> 基于 [NET10_WINUI3_WIN11_REFACTOR_PLAN.md](C:/WorkSpace/XX-Net/NET10_WINUI3_WIN11_REFACTOR_PLAN.md) 细化。本文档只关注可执行任务，不重复展开背景论证。

## 1. 使用方式

- 按阶段执行，不要跳阶段。
- 每个项目先完成 `P0`，再进入 `P1/P2`。
- 每个任务完成后必须补测试、验收记录和风险备注。
- 任何涉及协议行为变更的任务，必须先补兼容性测试。

## 2. 交付阶段

### 阶段 A：Solution 骨架与基础设施

目标：

- `XXNet.Net10.sln` 可编译
- WinUI 3 桌面壳可启动
- 后台 Host 可启动
- IPC 可连通

### 阶段 B：Windows 集成与控制面

目标：

- 托盘、系统代理、配置、日志、诊断打通
- 替代旧版 `launcher + web_control + win_tray`

### 阶段 C：代理入口与最小可用链路

目标：

- HTTP/SOCKS 代理入口可用
- 后台基本状态可观察
- 能打通最小 X-Tunnel 链路

### 阶段 D：X-Tunnel 与 Transport 完整重写

目标：

- 会话、调度、连接池、front 评分可用
- 性能与稳定性达到验收线

### 阶段 E：升级、发布、灰度

目标：

- 可安装、可升级、可回滚、可灰度

## 3. Solution 级任务

## 3.1 `XXNet.Net10.sln`

### P0

- [ ] 新建 `XXNet.Net10.sln`
- [ ] 加入全部 `src/*` 项目
- [ ] 加入全部 `tests/*` 项目
- [ ] 统一 `Directory.Build.props`
- [ ] 统一 `Directory.Packages.props`
- [ ] 统一 `global.json`
- [ ] 打开 nullable、隐式 using、分析器、TreatWarningsAsErrors
- [ ] 配置 `Debug/Release`、`win-x64` 发布参数

### P1

- [ ] 配置 CI 构建脚本
- [ ] 配置测试脚本
- [ ] 配置打包脚本

### 验收

- [ ] `dotnet build XXNet.Net10.sln` 通过
- [ ] `dotnet test XXNet.Net10.sln` 中基础空测试通过

## 4. 项目级任务

## 4.1 `src/XXNet.Contracts`

职责：

- 定义 Desktop 与 ServiceHost 间的 IPC 合同
- 定义状态 DTO、命令 DTO、事件 DTO

### P0

- [ ] 建立 `Commands/`
- [ ] 建立 `Events/`
- [ ] 建立 `Dtos/`
- [ ] 建立 `Enums/`
- [ ] 定义 `AppStatusDto`
- [ ] 定义 `ProxyStatusDto`
- [ ] 定义 `TunnelStatusDto`
- [ ] 定义 `ConnectionSnapshotDto`
- [ ] 定义 `EnableSystemProxyCommand`
- [ ] 定义 `DisableSystemProxyCommand`
- [ ] 定义 `RestartTunnelCommand`
- [ ] 定义 `ReloadConfigCommand`
- [ ] 定义 `ExportDiagnosticsCommand`

### P1

- [ ] 定义实时事件流 DTO
- [ ] 定义升级命令 DTO
- [ ] 定义错误码与标准错误响应

### 测试

- [ ] DTO 序列化兼容测试
- [ ] 向后兼容字段测试

### 验收

- [ ] 所有 IPC 模型可序列化
- [ ] 不包含 UI/平台依赖

## 4.2 `src/XXNet.Core`

职责：

- 核心配置、通用模型、时间、重试、错误码、运行时选项

### P0

- [ ] 建立 `Configuration/`
- [ ] 建立 `Options/`
- [ ] 建立 `Abstractions/`
- [ ] 建立 `Errors/`
- [ ] 建立 `Timing/`
- [ ] 建立 `Retry/`
- [ ] 定义 `AppOptions`
- [ ] 定义 `ProxyOptions`
- [ ] 定义 `TunnelOptions`
- [ ] 定义 `WindowsOptions`
- [ ] 实现 `ConfigRepository`
- [ ] 实现配置版本号与迁移入口
- [ ] 实现统一时钟抽象
- [ ] 实现统一错误码定义

### P1

- [ ] 实现配置变更通知
- [ ] 实现敏感字段脱敏
- [ ] 实现运行配置快照

### 测试

- [ ] 默认配置测试
- [ ] 配置读写测试
- [ ] 损坏配置恢复测试
- [ ] 配置迁移测试

### 验收

- [ ] 配置可稳定读写
- [ ] 旧配置可迁移

## 4.3 `src/XXNet.Diagnostics`

职责：

- 结构化日志、EventSource、指标、诊断包、崩溃上下文

### P0

- [ ] 建立 `Logging/`
- [ ] 建立 `Telemetry/`
- [ ] 建立 `DiagnosticsBundle/`
- [ ] 定义日志字段规范
- [ ] 实现 Logger 初始化
- [ ] 实现会话 ID / 连接 ID 关联
- [ ] 实现 `AppEventSource`
- [ ] 实现关键事件点埋点
- [ ] 实现诊断包导出服务

### P1

- [ ] 接入性能计数快照
- [ ] 接入异常现场快照
- [ ] 接入日志裁剪与保留策略

### 测试

- [ ] 日志格式测试
- [ ] 诊断包内容测试
- [ ] 高并发日志不丢失测试

### 验收

- [ ] 出问题时能导出足够复盘材料

## 4.4 `src/XXNet.Windows`

职责：

- Windows 11 平台能力封装

### P0

- [ ] 建立 `Proxy/`
- [ ] 建立 `Tray/`
- [ ] 建立 `Startup/`
- [ ] 建立 `Security/`
- [ ] 建立 `Instance/`
- [ ] 建立 `Process/`
- [ ] 实现系统代理启停
- [ ] 实现系统代理状态检测
- [ ] 实现单实例唤起
- [ ] 实现托盘图标与菜单
- [ ] 实现开机启动注册
- [ ] 实现进程退出清理

### P1

- [ ] 实现证书安装/卸载
- [ ] 实现管理员权限检查与提权协作
- [ ] 实现通知弹窗

### P2

- [ ] 实现事件日志写入
- [ ] 实现更细粒度系统冲突检测

### 测试

- [ ] 系统代理开启/关闭测试
- [ ] 幂等启停测试
- [ ] 异常退出恢复测试
- [ ] 单实例测试

### 验收

- [ ] 可完全替代旧版 `win32_proxy_manager.py` 和 `win_tray.py`

## 4.5 `src/XXNet.ServiceHost`

职责：

- 后台宿主、依赖注入、HostedService 编排、IPC Server

### P0

- [ ] 建立 `HostedServices/`
- [ ] 建立 `Ipc/`
- [ ] 建立 `Composition/`
- [ ] 实现 `Program.cs`
- [ ] 注册 Core/Windows/Proxy/XTunnel/Transport/Diagnostics
- [ ] 实现服务启动顺序
- [ ] 实现服务停止顺序
- [ ] 实现 Named Pipes Server
- [ ] 实现健康探针

### P1

- [ ] 实现后台守护模式
- [ ] 实现 UI 断开后继续运行
- [ ] 实现故障自恢复策略

### 测试

- [ ] Host 启停测试
- [ ] IPC 连接测试
- [ ] 多命令并发测试

### 验收

- [ ] 后台可独立运行
- [ ] UI 断开不影响代理核心

## 4.6 `src/XXNet.Desktop`

职责：

- WinUI 3 前端、页面导航、ViewModel、状态展示

### P0

- [ ] 建立 `Views/`
- [ ] 建立 `ViewModels/`
- [ ] 建立 `Services/`
- [ ] 实现 `App.xaml`
- [ ] 实现 `MainWindow.xaml`
- [ ] 实现启动页壳层
- [ ] 实现状态页
- [ ] 实现设置页
- [ ] 实现日志页
- [ ] 实现诊断页
- [ ] 接入 IPC Client
- [ ] 接入托盘交互

### P1

- [ ] 实现连接详情页
- [ ] 实现实时图表
- [ ] 实现更新页
- [ ] 实现错误引导页

### P2

- [ ] 实现高级诊断模式
- [ ] 实现实验性设置页

### 测试

- [ ] ViewModel 单元测试
- [ ] 基础导航测试
- [ ] IPC 状态刷新测试

### 验收

- [ ] 不依赖浏览器控制台
- [ ] 能完成主要运维动作

## 4.7 `src/XXNet.Proxy`

职责：

- 入站代理监听与协议处理

### P0

- [ ] 建立 `Listeners/`
- [ ] 建立 `Common/`
- [ ] 建立 `Socks/`
- [ ] 建立 `Http/`
- [ ] 建立连接上下文模型
- [ ] 实现 TCP 监听服务
- [ ] 实现 SOCKS4
- [ ] 实现 SOCKS4a
- [ ] 实现 SOCKS5 无认证
- [ ] 实现 HTTP CONNECT
- [ ] 实现普通 HTTP 代理
- [ ] 实现读写超时
- [ ] 实现取消传播

### P1

- [ ] 实现更细的异常原因分类
- [ ] 实现连接级指标
- [ ] 实现限流与并发保护

### P2

- [ ] 评估 IPv6 完整路径
- [ ] 评估认证预留扩展点

### 测试

- [ ] SOCKS4/4a 协议测试
- [ ] SOCKS5 协议测试
- [ ] HTTP CONNECT 测试
- [ ] 普通 HTTP 代理测试
- [ ] 超时测试
- [ ] 取消测试
- [ ] 半关闭连接测试

### 验收

- [ ] 可替代旧版 `proxy_handler.py` 的核心入站能力

## 4.8 `src/XXNet.Transport`

职责：

- 出站连接、TLS、HTTP/1.1、HTTP/2、连接池、worker 调度

### P0

- [ ] 建立 `Connections/`
- [ ] 建立 `Tls/`
- [ ] 建立 `Protocols/`
- [ ] 建立 `Dispatch/`
- [ ] 定义连接抽象
- [ ] 实现连接池
- [ ] 实现 worker 生命周期
- [ ] 实现 HTTP/1.1 transport
- [ ] 实现 HTTP/2 transport
- [ ] 实现 keep-alive
- [ ] 实现连接关闭原因码

### P1

- [ ] 实现 RTT 统计
- [ ] 实现吞吐统计
- [ ] 实现 front 健康检查
- [ ] 实现空闲回收

### P2

- [ ] 评估 ALPN / 握手差异
- [ ] 必要时补定制 transport 适配层

### 测试

- [ ] 连接池测试
- [ ] worker 调度测试
- [ ] keep-alive 测试
- [ ] HTTP/2 复用测试
- [ ] 连接关闭原因测试

### 验收

- [ ] 可替代 `front_base` 中连接池与调度主链路

## 4.9 `src/XXNet.XTunnel`

职责：

- 会话、连接注册、ACK、重试、front 评分、链路恢复

### P0

- [ ] 建立 `Sessions/`
- [ ] 建立 `Connections/`
- [ ] 建立 `Flow/`
- [ ] 建立 `Dispatch/`
- [ ] 定义消息模型
- [ ] 实现 `SessionCoordinator`
- [ ] 实现连接注册表
- [ ] 实现 ACK 跟踪
- [ ] 实现超时重试
- [ ] 实现最小会话可用链路

### P1

- [ ] 实现 front 评分
- [ ] 实现失败惩罚与衰减
- [ ] 实现多连接调度
- [ ] 实现健康快照输出

### P2

- [ ] 实现高级流控
- [ ] 实现更细粒度恢复策略

### 测试

- [ ] 会话建立测试
- [ ] 会话关闭测试
- [ ] ACK/重试测试
- [ ] front 切换测试
- [ ] 网络抖动恢复测试

### 验收

- [ ] 可打通实际 X-Tunnel 最小链路

## 4.10 `src/XXNet.Updater`

职责：

- 独立升级、替换、回滚

### P0

- [ ] 建立升级器入口
- [ ] 定义升级元数据格式
- [ ] 定义安装目录布局
- [ ] 实现下载与校验
- [ ] 实现替换流程
- [ ] 实现回滚流程

### P1

- [ ] 实现静默升级
- [ ] 实现 UI 协同升级
- [ ] 实现失败恢复报告

### 测试

- [ ] 成功升级测试
- [ ] 失败回滚测试
- [ ] 进程占用测试

### 验收

- [ ] 升级失败不破坏可运行版本

## 5. 测试项目任务

## 5.1 `tests/XXNet.Core.Tests`

- [ ] 配置读写
- [ ] 配置迁移
- [ ] 默认值
- [ ] 错误码

## 5.2 `tests/XXNet.Windows.Tests`

- [ ] 系统代理启停
- [ ] 单实例
- [ ] 异常退出清理

## 5.3 `tests/XXNet.Proxy.Tests`

- [ ] SOCKS4/4a/5
- [ ] HTTP CONNECT
- [ ] HTTP 正向代理
- [ ] 超时与取消

## 5.4 `tests/XXNet.Transport.Tests`

- [ ] 连接池
- [ ] HTTP/1.1
- [ ] HTTP/2
- [ ] keep-alive
- [ ] worker 调度

## 5.5 `tests/XXNet.XTunnel.Tests`

- [ ] 会话建立/关闭
- [ ] ACK/重试
- [ ] front 切换
- [ ] 故障恢复

## 5.6 `tests/XXNet.Integration.Tests`

- [ ] Desktop 到 ServiceHost IPC
- [ ] 系统代理到本地监听
- [ ] 本地监听到 X-Tunnel 最小链路
- [ ] 升级与回滚链路

## 5.7 `tests/XXNet.Perf.Tests`

- [ ] 冷启动耗时
- [ ] 系统代理启停耗时
- [ ] 100 并发短连接
- [ ] 500 并发短连接
- [ ] 30 分钟长稳

## 6. 执行顺序

### 里程碑 1

- [ ] `XXNet.Net10.sln`
- [ ] `XXNet.Contracts`
- [ ] `XXNet.Core`
- [ ] `XXNet.Diagnostics`
- [ ] `XXNet.ServiceHost`
- [ ] `XXNet.Desktop`

输出：

- WinUI 壳可启动
- Host 可启动
- IPC 可连通

### 里程碑 2

- [ ] `XXNet.Windows`
- [ ] `XXNet.Desktop`
- [ ] `XXNet.ServiceHost`

输出：

- 托盘
- 系统代理
- 设置页
- 日志页

### 里程碑 3

- [ ] `XXNet.Proxy`
- [ ] `XXNet.Contracts`
- [ ] `XXNet.ServiceHost`

输出：

- HTTP/SOCKS 入站可用

### 里程碑 4

- [ ] `XXNet.Transport`
- [ ] `XXNet.XTunnel`
- [ ] `XXNet.ServiceHost`

输出：

- 最小 X-Tunnel 链路可用

### 里程碑 5

- [ ] `XXNet.Updater`
- [ ] `tests/*`
- [ ] 打包脚本

输出：

- 可升级
- 可回滚
- 可灰度

## 7. 完成定义

- [ ] WinUI 3 前端可替代浏览器控制台
- [ ] 后台可独立运行
- [ ] 系统代理可稳定接管与恢复
- [ ] HTTP/SOCKS 入站可用
- [ ] X-Tunnel 最小链路可用
- [ ] 24 小时稳定性测试通过
- [ ] 升级与回滚通过
- [ ] 用户无需 Python 运行时

## 8. 建议先开的真实工单

### 工单 1

- [ ] 新建 `XXNet.Net10.sln`
- [ ] 新建 `XXNet.Contracts`
- [ ] 新建 `XXNet.Core`
- [ ] 新建 `XXNet.Diagnostics`

### 工单 2

- [ ] 新建 `XXNet.ServiceHost`
- [ ] 打通 Generic Host
- [ ] 打通 Named Pipes Server

### 工单 3

- [ ] 新建 `XXNet.Desktop`
- [ ] 打通 WinUI 3 主窗口
- [ ] 打通 Named Pipes Client

### 工单 4

- [ ] 新建 `XXNet.Windows`
- [ ] 打通系统代理启停
- [ ] 打通托盘

### 工单 5

- [ ] 新建 `XXNet.Proxy`
- [ ] 先实现 SOCKS5
- [ ] 再实现 HTTP CONNECT

### 工单 6

- [ ] 新建 `XXNet.Transport`
- [ ] 先实现连接池与 HTTP/1.1

### 工单 7

- [ ] 新建 `XXNet.XTunnel`
- [ ] 先实现最小会话模型与 ACK

### 工单 8

- [ ] 新建 `XXNet.Updater`
- [ ] 先实现回滚安全骨架
