# Shakur et al. (2026) — OASIS: A Rubric-Based Multimodal Assessment Platform Using LLMs 文献精读

> 定位：本项目**最接近的现成参考实现**——OASIS 在医学教育里做了和约师几乎一样的事，验证了"rubric + 多模态 + 证据 + 人工复核"路线可行

---

## 1. 文献信息

| 项 | 内容 |
|---|---|
| 标题 | OASIS: A Rubric-Based Multimodal Assessment Platform Using Large Language Models |
| 作者 | Ameer H. Shakur, Shinyoung Kang, David Hein, Michael J. Holcomb, Huong-Tra Ngo, Aarash Zakeri, Minhan Park, Licheng Yi, Dhanush Jain, Hunter Schuler, Andrew R. Jamieson |
| 期刊 | arXiv:2609.09180（cs.SE），2026，技术报告（27 页） |
| 机构 | UT Southwestern Medical Center（Jamieson Lab） |
| 类型 | 系统 / 技术报告（**非开源代码**，只发布报告与项目信息） |
| 关键词 | rubric-based assessment、multimodal、LLM、encounter management、provenance、human review |

> 原文：arXiv [2609.09180](https://arxiv.org/abs/2609.09180) · [项目页](https://jamiesonlabutsw.github.io/oasis/)

---

## 2. 一句话概括

**OASIS**（Open Assessment and Scoring Infrastructure Stack）是一个**用 LLM 对音视频 / 文本按 rubric 打分**的生产级平台——单件打分很容易，但**大规模部署**需要 encounter 管理、rubric 版本化、多模态编排、溯源留存、人工复核；OASIS 把这些工程问题都解决了，已在 UT Southwestern **生产运行 7,000+ 次**。

---

## 3. 核心问题

用 LLM 评一个东西很简单；但**在大规模、可审计、可复核**的前提下评成千上万个东西，系统层面需要什么？

---

## 4. OASIS 是什么（架构）

| 组成 | 作用 |
|---|---|
| 独立 CLI + Elephant/MAPLES 集成栈 | encounter（个案）管理 + 多模态评分编排 |
| 模型接入 | 既支持**托管 API**，也支持**自托管开源模型**（Ollama、vLLM、OpenAI 兼容端点） |
| SimRubrics | rubric 编写工具（可选扩展） |
| Wayfinder | 对话式 agent 网关（可选扩展） |

**输出**：给定 rubric + 录制的 encounter，产出 **逐标准得分（per-criterion scores）+ 证据（evidence）+ 理由（rationales）**，并留存执行产物供审计。

---

## 5. 六个关键设计特征

| 特征 | 含义 |
|---|---|
| **rubric-as-program compilation** | rubric 编译成可执行程序 |
| **progressive execution plans** | 渐进式执行计划 |
| **content-addressable grading identity** | 内容寻址的评分身份（幂等 / 去重） |
| **transcript-augmented multimodal grading** | **转写增强的多模态评分**：音频先转写，再按文本打分（文本-only 端点也能参与） |
| **explicit review state** | 显式复核状态 |
| **shared command surface** | 人类与自主 agent 共用同一命令界面 |

---

## 6. 对本项目的作用

### 6.1 这是"同款系统"的生产级先例

OASIS 在**医学教育**里做的事，和约师在**数学家教**里要做的事**几乎一模一样**：录制表现 → rubric 分维度打分 → 给证据和理由 → 人工复核。它**生产运行 7,000+ 次**，强烈验证了约师路线的可行性。

### 6.2 输出结构几乎一致

OASIS 的输出是 **per-criterion scores + evidence + rationales**——这正是约师 [scoring-prompt.md](../scoring-prompt.md) JSON schema 里的 **level（维度得分）+ evidence（证据）+ rationale（理由）**。**设计撞车，说明方向对**。

### 6.3 "转写增强的多模态" = 约师的 Tier 1 简化

OASIS 的 **transcript-augmented grading**（音频先转写、再按文本评）正是约师"音频 → ASR → 文本评分"的 Tier 1 方案。这印证了：**不直接分析音频、先转写成文本再评**，是被生产环境验证过的可行简化。

### 6.4 工程要素清单可对照

OASIS 列的工程要素（encounter 管理、rubric 版本化、provenance 溯源、review 状态）几乎就是约师 [functional_spec.md](../requirements/functional_spec.md) 里的模块（FR-1 题库 / FR-9 rubric 配置 / FR-5.7 版本追溯 / FR-6 人工复核）。**约师的功能清单不缺关键件**。

### 6.5 注意：这是报告，不是代码

论文明确声明**不含源代码、二进制、安装材料**。所以只能**借鉴架构与设计决策**，代码仍需约师自研或拼接开源件（见 [open-source-stack.md](../open-source-stack.md)）。

---

## 7. 关键启示

1. **路线可行**：rubric + 多模态 + 证据 + 人工复核，有 7,000+ 次的生产级先例。
2. **输出结构对齐**：per-criterion scores + evidence + rationales = 约师的维度得分 + 证据 + 理由，方向正确。
3. **转写优先是对的**：audio → transcript → text grading = 约师的 Tier 1 简化，已被验证。
4. **工程要素要对齐**：encounter 管理、rubric 版本化、provenance、review 状态都要有——约师清单不缺。
5. **只能借鉴架构**：这是报告非代码，实现仍需自研 / 拼接。
