# 本地补查与全文对照：真实论文验证记录

记录日期：2026-11-10。本轮实现“说明缺失证据 → 在同一份本地论文中补查一次 → 客户端重新判断 → 展示前后记录”。服务端没有增加模型 API。操作和阅读顺序见[本地补查导读](local_followup_guide.md)，执行与计分方式见[评测导读](local_followup_evaluation_guide.md)。

## 实际结果

这批 15 条定向样本中，本地补查和同一客户端直接读取已解析正文都给出了 **10 条正确的明确判断，另外 5 条保留证据不足**；两条路径均没有错误的明确判断，最终标签均与预先冻结的参考标签一致。补查没有测出语义准确率优势，测到的收益是使用更少的上下文，并留下缺口、查询、引文和前后判断的记录。

| 指标 | 开发批直接正文 | 开发批本地补查 | 验证批直接正文 | 验证批本地补查 |
| --- | ---: | ---: | ---: | ---: |
| 样本数 | 9 | 9 | 6 | 6 |
| 最终标签与参考标签一致 | 9/9 | 9/9 | 6/6 | 6/6 |
| 正确的支持/反驳判断 | 6/9 | 6/9 | 4/6 | 4/6 |
| 错误的明确判断 | 0 | 0 | 0 | 0 |
| 仍为证据不足 | 3 | 3 | 2 | 2 |
| 反驳召回 | 3/3 | 3/3 | 2/2 | 2/2 |
| 有效模型调用数，含共同初判 | 18 | 18 | 12 | 12 |

初次摘要判断全部为证据不足，正确明确判断为 **0/15**。摘要参考标签也全为证据不足，所以“摘要标签一致率 15/15”不能被当成解决了 15 个问题。补查后 10 条正确给出支持或反驳，余下 5 条的全文参考标签仍为证据不足；没有把“更快”“点估计更好”等内容扩张成未报告的电量、置信区间或显著性结果。

两条最终路径逐例标签相同：本地补查相对直接正文 0 胜、0 负、15 同对。这是小样本观察，不是等效性证明或通用准确率 100% 的证据。真实材料中的明确结论仍来自客户端模型，MCP 不认证它的科学正确性。

| 模型用量，均含共同初判 | 直接正文 | 本地补查 |
| --- | ---: | ---: |
| 输入 token | 527,441 | 379,351 |
| 其中缓存输入 token | 61,824 | 70,656 |
| 输出 token | 39,474 | 25,211 |
| 单独报告的推理输出 token | 6,326 | 6,633 |
| 模型调用耗时之和 | 1,186.435 秒 | 891.498 秒 |

本地补查的输入 token 少 **28.08%**，输出 token 少 **36.13%**；推理输出却多 **4.85%**，不能说所有用量都降低。推理计数单列，不再加进输出总数。开发/验证输入减少分别为 31.54%/22.38%。这些比例仅针对这版整理文本、客户端和提示，不能换算成未测量的费用或人工时间。调用耗时之和含客户端启动与服务延迟，不是独立端到端速度试验。

实际执行 45 次 CLI 调用、45 个独立会话；共同初判 15 次只执行一次，按路径计费时各计入一次。因此实际总量是输入 741,566、输出 53,655、缓存输入 97,152、推理输出 9,088；两批运行墙钟合计 1,239.407 秒。没有运行器重试、答案修补、执行失败或观测到的工具调用。

共同检查器接受全部 45 个原始判断，91 处引文均逐字有效；这与语义一致率分开统计。实际 MCP 保存了 30 条初判/补查后记录，15 次本地查询都返回候选增量，但其中只有 10 条最终取得正确的明确判断，不能把 ADDED 当成 15 次语义成功。单次检索最多三段，但段落会切成多个证据单元，证据单元数并非命中段落数。

独立复算确认 45 个会话没有跨分区复用，91 处引文全部能回溯到原始 PDF 提取文本，并核对了 5,698 个证据来源切片。15 次检索都增加了原摘要以外的原文覆盖；955 个新增候选单元中，19 个重复覆盖了已见的原始摘要，另有 3 个跨越整理文本的生成分隔行与原文边界，这 3 个均未被模型引用。它们没有改变本轮得分，但说明候选单元数不能代替独立证据数。详见本地 `review/results/final_result_audit.md` 与 `combined_audit.json`。

汇总报告包含 **15 条审查链、30 个判断快照**，位于本地 `combined_report_01/review_report.html`。它通过原项目 MCP 导出，使用原始记录的逐字副本，没有改变两个冻结运行目录或再次调用模型。可追踪的例子包括：

- `dev_001`：摘要只说明吞吐量提高，补查后找到 LoRA 脚注中的 43.1 tokens/s/V100 及相同模型并行分片条件，转为支持。该页另有一般实验使用 A100 的说明；本样本特意限定为脚注报告的条件，不能外推为全部实验均使用 V100。
- `dev_006`：正文给出 BERT No NSP 的 QNLI 点估计，但没有支持论断指定置信区间的证据，保留证据不足。
- `validation_006`：论断把 iPhone 上的 71% 加速解释为包含 tokenization；原文的时间范围排除了它，因此补查后给出反驳。

## 逐例结果

下表保留全部论断。初判均为证据不足；两条最终路径均等于所列参考标签。每条原始答案、查询和引文见冻结目录。

| ID | 论文 | 完整论断 | 全文参考标签 / 两路径最终结果 |
| --- | --- | --- | --- |
| dev_001 | lora | For GPT-3 175B with the same number of model-parallel weight shards as full fine-tuning, LoRA's reported training throughput was 43.1 tokens per second per V100 GPU. | 支持 |
| dev_002 | transformer | The Transformer base model achieved 27.3 BLEU on the WMT 2014 English-to-German newstest2014 evaluation. | 支持 |
| dev_003 | transformer | For machine translation decoding, the Transformer paper used beam search with a beam size of 8. | 反驳 |
| dev_004 | lora | In LoRA's low-rank update parameterization, matrix A is initialized to zeros. | 反驳 |
| dev_005 | bert | In BERT's pre-training-task ablation, the bidirectional No NSP model achieved 84.9% QNLI development-set accuracy. | 支持 |
| dev_006 | bert | BERT's No NSP ablation has a reported 95% confidence interval of 84.1% to 85.7% for QNLI development-set accuracy. | 证据不足 |
| dev_007 | lora | For GPT-3 175B, LoRA reduced measured training electricity consumption by 20% compared with full fine-tuning. | 证据不足 |
| dev_008 | transformer | The Transformer base model's English-to-German BLEU score has a reported 95% confidence interval of 26.9 to 27.7. | 证据不足 |
| dev_009 | bert | The English Wikipedia corpus used for BERT pre-training contained 800 million words. | 反驳 |
| validation_001 | resnet | In the ResNet paper's Table 2 comparison, the 34-layer residual network had 25.03% top-1 error on ImageNet validation with 10-crop testing. | 支持 |
| validation_002 | distilbert | Replacing BERT-base with DistilBERT doubled the iPhone 7 Plus battery life in the paper's question-answering application. | 证据不足 |
| validation_003 | distilbert | DistilBERT's reported CPU inference time for a full pass of the STS-B development set with batch size 1 was 410 seconds. | 支持 |
| validation_004 | resnet | On CIFAR-10, the ResNet paper's 1202-layer network had a better test result than its 110-layer network. | 反驳 |
| validation_005 | resnet | The ImageNet validation top-1 error reduction from the 34-layer plain network to the 34-layer residual network was statistically significant at p < 0.001. | 证据不足 |
| validation_006 | distilbert | The reported 71% DistilBERT speedup over BERT on an iPhone 7 Plus includes tokenization time. | 反驳 |

## 材料与对照

使用五篇版本固定的原始论文，共 74 页。论断和参考判断由材料助手编制或扰动，保留出处、歧义说明和摘要/全文两套标签。它们是有目的地选取的真实来源样本，不是自然 benchmark，也不是独立专家标注。每篇包含可在正文查到的结果、与正文相反的细节，以及没有充分证据的额外要求。

| 分区 | 论文 | 固定版本 |
| --- | --- | --- |
| 开发，9 条 | Attention Is All You Need | [1706.03762v7](https://arxiv.org/abs/1706.03762v7) |
| 开发，9 条 | BERT | [1810.04805v2](https://arxiv.org/abs/1810.04805v2) |
| 开发，9 条 | LoRA | [2106.09685v2](https://arxiv.org/abs/2106.09685v2) |
| 验证，6 条 | Deep Residual Learning for Image Recognition | [1512.03385v1](https://arxiv.org/abs/1512.03385v1) |
| 验证，6 条 | DistilBERT | [1910.01108v4](https://arxiv.org/abs/1910.01108v4) |

每篇三条论断。两组论文不重叠；模型可能在训练中见过这些著名论文，因此不能称为模型未见过的论文测试。任务刻意选择摘要之外的信息，不能估计一般用户问题中有多少会从补查受益。

准备时为解析器添加经原始网页核对的标题、arXiv DOI 和真实摘要前置信息，随后保留完整、未经改写的 PDF 提取文本。没有移除断行、连字或表格线性化。摘要前置副本与原始提取中的摘要都保留，存在重复覆盖；候选单元数量不等于新增科学证据数量。原始 PDF、物理页坐标和双向文本映射都留在本地。这轮不测试任意原始 PDF 的自动元数据识别、OCR 或复杂版面适配。

每条先共享一次摘要判断。`fulltext_direct` 再独立读取同篇论文的全部可解析正文；`local_followup` 根据已保存的一个缺口，通过实际 MCP 检索至多三段及相邻上下文后再判断。两条路径都获得原论断和原始初判，使用相同语义说明、结构化输出和检查器，不给任一组加入 MCP 启发式分数。可见文本分别为正文和检索子集，不是完全相同的证据包。

这里的“全文对照”仅指当前解析器保留的正文，止于 References，不是 PDF 的所有页。开发批的正文结束在 LoRA 第 13/26 页、Transformer 第 10/15 页、BERT 第 9/16 页附近；验证批为 ResNet 第 8/12 页、DistilBERT 第 5/5 页的 References 之前。参考文献后的附录没有进入模型上下文。选定的决定性证据都在当前范围内，因此可以核对这批标签，但不能声称已经覆盖整篇论文的附录内容。

每条每路径最多两次有效调用，包含共同初判。实际总预算最多 3N 次，因为初判只执行一次。全文路径每条执行第二次调用；补查路径只对符合条件的未决记录调用。错误、拒绝和未补查病例仍在分母内；不修复或重试模型答案。

实际判断使用独立 Codex CLI 上下文，请求 `gpt-6.1-sol`、推理 `high`，CLI `0.167.0-alpha.3.2`。具体后台模型快照和完整系统提示未知；这是现有客户端对照，不是无系统提示的裸 API。运行器请求禁用其他工具、记忆和技能，逐次保存原始事件并拒绝观察到的工具使用或会话复用。CLI 内部传输重试不能由调用次数推断。

## 冻结与证据保存

协议 `local_evidence_followup_v1`，运行代码为干净提交 `7108a4beeda5fa122a1443881051659be438f8a6`。两批计划都在第一次正式模型判断前冻结，开发结果不会用于修改验证提示或检索。计分仅在完整运行收据和哈希检查通过后读取对应分区的标签。

本地证据根目录：`D:/Internship/Academic code/audit_guardrail_20261110_local_followup/`。

| 内容 | 本地证据 |
| --- | --- |
| 原 PDF、提取文本、整理文本及映射 | `materials/originals/`、`extracted/`、`refs/`、`maps/` |
| 来源版本、标签制定和文件哈希 | `materials/material_receipt.json`、`source_manifest.json`、`freeze_receipt.json`、`partition_gold_receipt.json` |
| 冻结输入、来源、代码、提示与实际 MCP 包 | `dev_plan_01/`、`validation_plan_01/` |
| 实际命令、提示、事件、答案、MCP 收据及报告 | `dev_run_01/`、`validation_run_01/` |
| 各分区计分 | `dev_scores_01.json`、`validation_scores_01.json` |
| 独立审查和复算 | `review/independent_review.md`、`review/evaluation/`、`review/results/` |
| Python 与依赖版本 | `environment.json` |

开发标签 SHA-256 为 `eb3d598a6722bbc47ad4e33878d65244e31264dccf268a53a2b2f09363b00681`，验证标签为 `6c1735ad15729cd952fa983406340817aae77f4f67e85d3bb1947e952b22bc9e`。完整输入 SHA-256 为 `0da24b10c3053b0574a933296ad70bd95e9523b957ff2abdc7d5300c33808e3c`。

Git 保存代码、协议、导读和结果摘要，下载的论文与运行记录留在本地。冻结记录可重新计分；再次调用模型不保证相同答案。另有一条虚构材料的 CLI 兼容性试调用，独立保存在 `cli_preflight_01/`，不计入正式样本或正式成本。

## 工程验收与适用边界

工作副本全量测试 500 项通过；同步回原项目后再次全量测试仍为 500 项通过。实际 MCP stdio 验收包含准备、分页、记录、补查、再次记录、HTML 导出，以及指纹错误、重复请求、来源变化的拒绝；服务端外部访问尝试为零。安装包成功构建并检查入口和新增模块。它们是工程验证，不能替代模型结果。

独立审查复现并修复了中文无空格查询漏检、长摘要重新切块被误算新增、删除新记录摘要后触发旧记录兼容，以及评测提示/输入错配等问题。旧版 `5acfd012` 的实际包和记录仍可按原摘要回放。

这里的哈希用于发现错配和内容变化，不是对能够重写全部文件者的数字签名。逐字引用正确不证明语义推理正确；有限检索未找到内容也不能证明整篇论文从未讨论它。报告中仍然保留这些区别。

此前 [30 条 SciFact 同证据对照](paired_review_results.md) 的直接模型 22/30、MCP 21/30 等结果保持不变。本轮论文、问题、证据范围、调用预算和客户端版本均不同，不能把两个分数相减宣称反驳能力提升。
