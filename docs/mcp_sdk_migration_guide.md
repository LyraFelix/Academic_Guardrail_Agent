# MCP SDK 2.x 迁移与验证

本项目使用官方 Python SDK `mcp>=2.3.0,<3`。2026-11-18 核对的最新稳定版是 2.3.0；`<3` 表示下次主版本变化需要重新验证，2.x 内继续安装当前版本。这里的版本是实现 MCP 通信的 Python 库版本，不是本项目有几个 MCP 服务，也不是客户端大模型的版本。

## 为什么之前本地通过，GitHub 仍失败

提交 `c433e9c` 的 [CI 第 62 次运行](https://github.com/LyraFelix/Academic_Guardrail_Agent/actions/runs/42766763213) 中，Python 3.12 job 的结果为 `4 failed, 491 passed, 4 skipped`。项目声明 `mcp>=1.0.0`，但服务端仍导入 `mcp.server.fastmcp.FastMCP`。这个路径在 SDK 2.x 中已失效。此前本地 500 项测试使用的是旧的 SDK 1.27.2，只能证明旧环境的结果。

部分测试使用了 `pytest.importorskip`，把必需的 MCP 库不兼容当成可以跳过的情况。模块级跳过还会使统计数量不同，不能直接把云端数字与本地的 500 相减。现在必需依赖导入失败会直接导致测试失败。

官方依据：[PyPI 发行记录](https://pypi.org/project/mcp/)、[SDK 迁移说明](https://py.sdk.modelcontextprotocol.io/migration/)。2.0.0 的发行记录是 2026-07-28，2.3.0 是 2026-10-02，不是“10 月底才发布 2.x”。

## 按边界理解代码变化

1. **服务端入口：** `src/academic_guardrail/mcp_server.py` 改用 `from mcp.server import MCPServer`。仍由一个进程注册十个工具和一个提示词；显式声明项目版本，并使用 stdio 启动。
2. **客户端读取结果：** SDK 的 Python 属性改为 `is_error`、`structured_content`、`input_schema`。`scripts/client_review_batch.py` 和各验收脚本都使用新属性。
3. **保存通信记录：** MCP 在线路上的 JSON 字段仍是 `isError`、`structuredContent` 等。只对 SDK 对象使用 `model_dump(mode="json", by_alias=True)`，让新日志继续保持标准协议字段。业务证据包的序列化和摘要计算没有跟着更名。
4. **可修正的工具错误：** SDK 2.x 会隐藏意外异常的详细内容。`expose_review_errors` 在 MCP 边界把输入校验失败、文件缺失和文件冲突转换为 `ToolError`，让客户端收到拒绝原因。底层核心函数继续抛普通 Python 异常，其他意外异常交给 SDK 处理。原有四个元数据/文档工具的文本返回契约保持原样。
5. **离线验收：** SDK 2.x 新增 HTTP 实现依赖 `httpx2`。验收子进程同时拦截现有 `httpx` 和 SDK 的 `httpx2` 出站方法；本地补查仍不调用模型。

没有添加单独的 `fastmcp` 框架，也没有编写 1.x/2.x 双版本兜底。业务逻辑不需要感知 SDK 版本，迁移集中在通信边界、依赖声明与验收脚本。

## 本地复现

在新环境中从仓库根目录执行，避免旧环境已经安装的包掩盖问题：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --upgrade -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts/validate_phase_two.py --output-dir scratch/phase_two
.\.venv\Scripts\python.exe scripts/validate_phase_three.py --output-dir scratch/phase_three
.\.venv\Scripts\python.exe scripts/validate_client_review.py --output-dir scratch/client_review
.\.venv\Scripts\python.exe -m scripts.validate_local_followup --output scratch/local_followup
```

验收输出目录必须尚不存在；再次运行请换新目录，保留前次证据。Linux 环境使用 `.venv/bin/python`。

`tests/test_mcp_transport.py` 启动真实子进程，而非直接调用 Python 工具函数。它交叉验证两种入口（带离线拦截的 `main()`、安装生成的 `academic-guardrail-mcp` 命令）和两种连接（既有 `initialize` 握手、新版 `discover`）。每种组合都检查工具清单、输入 schema、提示词、准备证据、读取证据、拒绝原因和保存的协议字段。

现有完整验收脚本进一步检查撤稿优先级、分页、错误摘要、伪造引用、一次补查限制、来源变化和 HTML 报告。这里的判断是脚本固定输入，用于验证工程链路，不是新大模型评测。

## CI 为什么要安装 wheel

`.github/workflows/ci.yml` 在 Ubuntu 的 Python 3.10–3.14 与 Windows 的 Python 3.12 上构建 wheel，安装该包及当前依赖，执行 `pip check`、全量测试和四条离线验收流程。测试不依赖之前机器上的 1.x 环境，也能发现包遗漏和命令行入口错误。

矩阵关闭 `fail-fast`，某个环境失败不会取消其他环境。每个 job 保存依赖版本、JUnit 测试报告、wheel 和验收记录为 GitHub artifact（保留 14 天）。查看失败时先找对应提交和具体 job，再看安装版本与错误，不能以本地通过推断云端通过。

历史实验目录和模型原始输出没有重写。SDK 兼容性测试通过，只说明这些工程接口在所测环境工作，不能提高或替代既有 benchmark 成绩。
