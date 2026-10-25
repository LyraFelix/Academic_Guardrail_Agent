# 第一阶段代码导读

这份文档帮助你从“会运行”走到“能解释、能修改”。先理解一个引用如何得到结果，再读查询细节；不用一开始通读所有文件。

## 1. 先明确这个项目做什么

输入是文献引用，以及可能包含引用的正文句子。系统分开回答：

1. 这条引用能否匹配到某篇文献或本地文件？
2. 当前查询来源是否给出了该文献的撤稿证据？
3. 可用参考文本中，哪些句子与正文相似，值得人工阅读？

第三个问题目前使用启发式方法。它不能证明事实、因果关系或数值一致性。`SUPPORTED` 是旧算法的内部标签，展示时解释为高相似度，而不是“已经证明断言成立”。

## 2. 一条调用链

```text
CLI / MCP
   │
   ▼
AuditService.verify_reference(citation)
   │
   ├─ 在线：ChineseAcademicProvider 收集候选、来源与异常
   └─ 离线：OfflineRetractionDB + LocalRefStore
   │
   ▼
decide_reference(citation, evidence)  ← 纯函数，不请求网络
   │
   ▼
VerificationResult
   │
   ├─ 单条 verify：输出元数据结果
   └─ 文档审计：存在可靠文本时做启发式比对
   │
   ▼
format_result / ReportGenerator
```

“纯函数”在这里意味着只读取输入并生成结果，不读文件、不查询 API。这让你可以用几行字典构造任何边界情况，直接测试判断是否正确。

## 3. 推荐阅读顺序

| 文件（相对仓库根目录） | 读的时候关注什么 |
| --- | --- |
| `src/academic_guardrail/core/models.py` | Citation 是输入，EvidenceSource 是来源，VerificationResult 是最终输出 |
| `src/academic_guardrail/core/reference_decision.py` | 分支优先级，哪些信息足以判定、哪些必须保留不确定性 |
| `tests/test_verification_boundaries.py` | 用真实失败案例理解为什么要有这些分支 |
| `src/academic_guardrail/core/service.py` | I/O 编排、超时、本地兜底，以及何时允许做文本比对 |
| `src/academic_guardrail/providers/chinese_academic.py` | 多源查询如何转成统一字典；成功、失败、空结果如何区分 |
| `src/academic_guardrail/core/ref_resolver.py` | DOI 合并、标题/作者/年份得分与候选差距 |
| `src/academic_guardrail/core/result_formatter.py` | 同一结果如何在 CLI 与 MCP 中一致展示 |
| `src/academic_guardrail/core/reporter.py` | HTML 转义、内联资源、搜索过滤，以及范围说明 |

保留 Provider 的字典接口是为了控制本次改动范围。进入服务层后，输出使用 Pydantic 模型约束字段。以后如果继续扩展，可把采集结果也迁移成类型模型，但没有必要先引入复杂框架。

## 4. 判定表

以下按从上到下的优先级判断。

| 证据情况 | 结果 | 原因 |
| --- | --- | --- |
| 文献身份存在歧义 | UNVERIFIED / WARNING | 候选的撤稿事实不能直接归属于输入引用 |
| 身份可靠，并有明确撤稿来源 | RETRACTED / DANGER | 保留来源，不被其他来源的无记录覆盖 |
| 只有标题等弱撤稿线索 | UNVERIFIED / WARNING | 可能是撤稿研究论文或撤稿通知，需要人工区分 |
| 可靠在线元数据命中 | VALID / PASS，范围 REFERENCE_METADATA | 只确认本次元数据匹配 |
| 可靠本地文件命中 | VALID / PASS，证据 LOCAL_MATCHED | 文件存在不等于出版状态已确认 |
| 只认出期刊名 | UNVERIFIED / NOTICE | 期刊存在不证明文章存在 |
| 请求超时、限流等 | UNVERIFIED / WARNING | 故障不是负面检索证据 |
| 离线库无命中 | UNVERIFIED / WARNING | 离线覆盖有限，未联网确认 |

撤稿状态另有四种：`CONFIRMED` 已有明确记录；`SUSPECTED` 只有线索；`NO_RECORD` 本次查询范围内没有记录；`NOT_CHECKED` 没有完成对当前文献的核验。不要把最后两种合并成“未撤稿”。

## 5. 三个可以自己走通的例子

**例一：已知撤稿 DOI。** 执行 `academic-guardrail verify "10.1038/nature12968" --offline`。服务不会创建 HTTP 客户端，直接查询内置的历史示例，输出 CONFIRMED、撤稿原因和 offline_database 来源。这个演示验证程序路径，不证明数据库覆盖完整。

**例二：未知 DOI。** 执行 `academic-guardrail verify "10.1234/unknown" --offline`。应看到 UNVERIFIED、OFFLINE_NO_MATCH、NO_RECORD。注意“没有记录”和“文献存在且未撤稿”之间差了两次证明。

**例三：两篇同名候选。** 阅读 `test_ambiguous_retracted_candidate_is_not_a_confirmed_retraction`。字典里同时有 matched=True、is_uncertain=True、is_retracted=True。优先检查歧义，结果必须是 WARNING，而不是 DANGER。你可以复制此测试修改输入，观察哪个字段改变了结论。

## 6. 如何加一个小改动

以“补充新的展示字段”为例：先在 models 中定义含义和默认值，再在收集数据的地方填入，最后让 formatter/report 展示。不要让 CLI 或 MCP 重新解释 matched 字典，否则同一篇文献又会在不同入口得到不同答案。

修 bug 时先写能失败的测试。测试应描述用户能观察到的行为，例如“两个冲突文件必须弃权”，而不是机械检查某行实现。Provider 测试模拟 HTTP；服务测试模拟 Provider；CLI/MCP 测试调用实际接口并检查输出。测试默认禁止真实 HTTP，避免偶然的缓存或网络状态把错误掩盖。

```powershell
python -m pytest tests/test_verification_boundaries.py -q
python -m pytest tests/test_provider_safety.py -q
python -m pytest tests/test_entrypoint_boundaries.py -q
python -m pytest tests -q
```

在本机可用 `D:\Anaconda\envs\pytorch\python.exe` 代替 python；请确认开发依赖装在所选环境里。Windows 沙箱可能限制 asyncio 的本机套接字初始化，这属于执行环境问题，与外部 API 成功无关。

## 7. 本次没有解决什么

本次重点是结论边界与工程一致性，没有重写解析器或语义算法。引用漏提取、同一文献多次出现的上下文、复杂 PDF、数值冲突、跨语言覆盖和评测可复现性仍需下一阶段处理。不要把全部测试通过等同于全部论文都能审对。

本地文件标题来自简易抽取。两个文件的元数据相同也可能正文不同，因此保持两个候选并弃权；需要使用者清理重复文件或补全作者、年份。本地无匹配和歧义目前都体现为没有可靠本地命中，后续可扩展更细的诊断结果。

## 8. 面试时怎么讲

可以解释一项实际工程取舍：“我把数据采集和风险判定拆开，统一 CLI/MCP 的判定入口；为来源冲突、身份歧义和离线误判写回归测试。明确的撤稿记录优先，但必须先确认属于同一篇文献。”

你应能手画上面的调用链，并解释为什么查不到不是不存在、相似不是支持、离线文件不是权威出版记录。这比背诵没有复现记录的准确率更有说服力。
