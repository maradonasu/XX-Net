根据原版 5.16.6 修改
=========
  1. Python 3 运行时收口与兼容层补齐

  - 多个入口和模块文件将 shebang 明确切到 python3，并移除了大量 urllib2、urlparse、ImportError 式的 Python 2 分支。
  - 新增 py3_compat.py 和 cgi_compat.py，把启动链路和 Web 控制台的兼容逻辑集中到显式兼容层。
  - launcher/web_control.py 的 multipart 解析补了 CONTENT-LENGTH，上传/表单解析行为更稳。

  2. DNS 能力升级

  - vendored dnslib 做了大规模同步，核心是 dns.py、client.py、server.py。
  - 新增和增强了 EDNS0、DNSSEC 标志位、IPv6 发包、更多 RR 类型（如 CAA、HTTPS、SSHFP、TLSA、LOC 等）。
  - 新增 digparser.py 和对应测试文件，说明这部分不是小修，而是整段依赖升级。

  3. TLS 与 HTTP/2 调度行为调整

  - openssl_wrap.py 在 Python 3 下收敛到内置 ssl 路径，不再优先尝试 boringssl_wrap。
  - ssl_wrap.py 增强了超时控制、SSLWantRead/Write 处理、TLS 选项约束（禁压缩、禁重协商、最低 TLS 1.2 等）。
  - http_common.py 和 http_dispatcher.py 调整了 HTTP/2 活跃连接的超时判定，减少活跃 H2 worker 被误判失败和过早淘汰。

  4. X-Tunnel 传输与前端选择策略调整

  - config.py 下调了多个超时和延迟参数，使超时检测、ACK、重试更激进。
  - front_dispatcher.py 新增 front 失败惩罚和衰减机制，并改用 time.monotonic()，使前端选择更偏向避开短期不稳定节点。
  - proxy_session.py 缩短了带上传数据请求的阻塞等待时间，减少长时间占住 worker。
  - proxy_handler.py 把 socket 读取改为 select 驱动的超时轮询，减少忙等。

  5. 其他 vendored 库同步

  - ecdsa 进行了完整升级，新增 ssh.py 和多组测试文件，补入更多 Brainpool 曲线与 DER 处理能力。
  - sortedcontainers 也有大幅同步，并删除了 sortedlistwithkey.py。
  - 这类改动更多是底层依赖能力和兼容面更新，但如果业务代码依赖旧内部结构，存在联动风险。
