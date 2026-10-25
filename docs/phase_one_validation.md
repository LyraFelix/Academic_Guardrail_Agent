# 第一阶段验证记录

验证日期：2026-10-22。基线提交：`f9c85d318aaa923d7204a71ebc27518c5fb4a014`。本阶段修改保持未提交状态。

## 已执行

- 完整测试：**127 passed in 15.10s**。使用本机 `D:\Anaconda\envs\pytorch\python.exe`；外部 HTTP 被测试夹具拦截，模型加载关闭，缓存隔离。新增用例先观察到失败再实现修复。
- 实际 MCP stdio：完成 initialize、列出 4 个工具、调用两个离线查询；内置 DOI 返回 CONFIRMED，未知 DOI 返回 UNVERIFIED/NO_RECORD。不是仅直接调用 Python 函数。
- CLI 离线样稿：提取 2 条引用，1 条 WARNING、1 条 DANGER，生成 HTML。
- wheel：`mcp_academic_guardrail-0.1.0-py3-none-any.whl` 构建成功；没有新增运行依赖。
- HTML/Markdown：测试外部活动资源、HTML 转义、空结果、来源与撤稿说明；搜索/风险筛选及主题切换做了独立 JavaScript 行为检查。
- 独立代码复核发现本地重复元数据掩盖歧义、文本输出漏撤稿原因；已补测试并修复。后续数据源复核由主线程完成。
- 原项目 72 个基线文件的 SHA-256 与审查快照一致，回写前再次核对。

## 证据位置

本机审查目录：`D:\Internship\Academic code\audit_guardrail_20261019`。

- `phase_one_tests.xml`：完整测试结果。
- `phase_one_mcp.json`、`verify_phase_one_mcp.py`：MCP 传输验证结果与脚本。
- `phase_one_demo.html`：离线演示报告。
- `snapshot_manifest.json`、`snapshot/`：原始审查快照。
- `phase_one_copy_manifest.json`：回写完成后生成的逐文件哈希清单。
- `phase_one_original_backup/`：回写前被修改文件的备份。

## 未验证与后续工作

浏览器工具因安全策略拒绝 `file://`，没有完成本地 HTML 的浏览器截图或布局视觉检查。已验证结构、转义、外部资源边界与筛选脚本；不将这些检查描述为视觉验收。

未进行真实在线 API 可用性测试、完整撤稿数据覆盖评估、嵌入模型质量评测或 LLM 基准评测。离线测试不能替代这些证据。解析完整性、重复引用上下文和启发式语义误判留在后续阶段；历史 benchmark 仍需重建。

复现命令（已安装开发依赖时）：

```powershell
python -m pytest tests -q
academic-guardrail verify "10.1038/nature12968" --offline
academic-guardrail audit docs/examples/sample_manuscript.md --offline -o report.html
```
