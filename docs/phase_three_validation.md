# 第三阶段验证记录

日期：2026-11-01。范围：数字、否定、因果与范围的规则检查，以及来源、服务和展示层整合。本记录只包含工程验证，不是模型或真实论文准确率结果。

## 基线与失败复现

- 基线提交：`d4f86981c2982aa1afa530f372c70388c9bd949d`；原有 **172 项测试通过**，20.64 秒。
- 保存旧算法在 50 个合成样例上的原始输出。90% 对 10% 曾返回 `0.94 / SUPPORTED`；否定、相关升级因果、部分扩成所有也曾返回支持标签。
- 首批 52 个新增断言先失败；服务整合测试先出现 5 个失败；独立审查追加的边界样例先出现 18 个失败。最终修复没有改用真实模型或联网结果。
- 实际入口演示暴露主体词被停用词表清空，二次复核发现逗号相隔的时间限定丢失；均先加失败回归，再修复。失败记录保留，未覆盖。

## 已执行验证

解释器：`D:/Anaconda/envs/pytorch/python.exe`。测试依赖沿用隔离目录 `D:/Internship/Academic code/audit_guardrail_20261019/deps`，使用 pytest-asyncio 插件，禁止真实 HTTP 与模型加载。

| 验证 | 观察结果 |
| --- | --- |
| 完整回归 | **264 passed**，17.94 秒；比基线增加 92 项 |
| 合成样例重放 | 50 个输入保存逐条命名结果；用于开发与回归，不是独立留出集 |
| 实际 CLI | 审计演示文件，退出码 0，HTML 展示四类规则代码 |
| 实际 MCP stdio | 一个服务列出并成功调用四个工具，保留原始输出 |
| 演示数据流 | 1 个文献条目、4 处正文引用；2 WARNING、2 NOTICE、0 PASS |
| 来源回溯 | 每条演示提示的原文可按文件字符位置截取得到 |
| 离线边界 | Provider 构造、HTTP send、模型初始化的禁止访问计数均为 0 |
| HTML 静态检查 | 不含外部活动资源；未依赖 CDN |
| 独立代码复核 | 20 个原始反例复测后不再出现旧错误；追加时间边界回归通过 |
| Wheel | 无网络、无新增依赖构建成功，85,069 字节 |

Wheel SHA-256：`0b51a6617984de9b1e9c92013180384a1d97bc2481b1c8a73303027abeaefbdb`。首次 pip 构建被 Windows 沙箱临时目录写权限阻断；在正常权限下用相同离线参数重跑成功。

测试命令为 `python -X utf8 -m pytest tests -q -p pytest_asyncio.plugin`（本机另设置隔离 PYTHONPATH、关闭自动插件加载并保存 JUnit XML）。入口验收为 `python -X utf8 scripts/validate_phase_three.py --output-dir <new-directory>`；构建为 `python -m pip wheel . --no-index --no-deps --no-build-isolation --wheel-dir <output>`。

完整本地证据根目录：`D:/Internship/Academic code/audit_guardrail_20261101_phase_three/`。关键文件是 `baseline.xml`、`baseline_semantic_outputs.json`、`semantic_red.xml`、`flow_red.xml`、`edge_red.xml`、`reviewer_probe.json`、`reviewer_recheck.json`、`final_suite.xml`、`entrypoints_second/validation.json`、`entrypoints_second/report.html` 与 `wheel_build.log`。验收 manifest 保存源文件和输入文件的 SHA-256。运行产物留在本地，不提交为项目研究结果。

## 兼容性与证据边界

旧五元素元组保留，但自动产生的状态标签已改变。测试也同步移除了“高相似度=支持”“冲突必须低分”“统计不显著=效果反向”等旧预期，改查具体提示和原文。旧 benchmark 标签映射尚未迁移。

本阶段没有验证线上 API 覆盖，没有下载或调用嵌入模型，没有真实论文标注集或模型轨迹实验。复杂语法、跨语言、跨句条件及未知计量表达仍需要人工阅读，规则可能漏报或过度提示。详情见 [代码导读](phase_three_guide.md)。
