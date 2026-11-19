# Thakur et al. (2025) — Judging the Judges: Evaluating Alignment and Vulnerabilities in LLMs-as-Judges 文献精读

> 定位：本项目"LLM 评分"的**风险警示**——在 zheng-2023 的三种 bias 之外，补充宽松偏差、prompt 复杂度敏感两个新漏洞

---

## 1. 文献信息

| 项 | 内容 |
|---|---|
| 标题 | Judging the Judges: Evaluating Alignment and Vulnerabilities in LLMs-as-Judges |
| 作者 | Aman Singh Thakur, Kartik Choudhary, Venkat Srinik Ramayapally, Sankaran Vaidyanathan, Dieuwke Hupkes |
| 会议 | GEM²（Fourth Workshop on Generation, Evaluation and Metrics），404–430，2025 |
| 机构 | 未集中标注（作者含 Dieuwke Hupkes，Meta AI） |
| 类型 | 实证 / 基准论文 |
| 关键词 | LLM-as-a-Judge、alignment、vulnerability、leniency bias、prompt complexity |

> 原文：[ACL Anthology 2025.gem-1.33](https://aclanthology.org/2025.gem-1.33/) · [PDF](https://aclanthology.org/2025.gem-1.33.pdf)

---

## 2. 一句话概括

让 **13 个模型当"评委"、给 9 个模型当"考生"打分**，发现：只有最大最强的模型才勉强和人类对齐，而且**仍会差多达 5 分**；更糟的是，评委普遍有**宽松偏差**、对**prompt 复杂度敏感**，且"百分比一致率"这个常用指标会掩盖真实偏差。

---

## 3. 核心问题

1. 不同规模的 LLM 当评委，和人类打分对齐到什么程度？
2. LLM 评委有哪些**具体的漏洞（vulnerability）**？
3. 常用的"一致率"指标，够不够衡量评委质量？

---

## 4. 方法

| 项 | 内容 |
|---|---|
| 评委（judge） | **13 个模型**，规模 / 家族各异 |
| 考生（exam-taker） | **9 个模型**（base + instruction-tuned） |
| 任务 | 评委给考生的回答打分，与人类分数比对 |
| 度量 | 一致率（percent agreement）、分数差、排序能力 |

---

## 5. 关键发现

### 5.1 只有大模型勉强对齐，但仍差 5 分

- 只有**最好（最大）的模型**与人类"合理对齐"
- 但即使如此，**仍与人类分数差多达 5 分**

### 5.2 度量陷阱：百分比一致率不够

- 评委**一致率很高，给出的分数却可能完全不同**（高一致率 ≠ 分数接近）
- 论文明确呼吁：需要 **beyond percent agreement** 的对齐度量（呼应 Li et al. 的 ICC 观点）

### 5.3 小模型 + 词汇度量也能排序

- 在"给考生排序"这件事上，**小模型甚至 `contains` 这类词汇度量**都能给出合理信号
- 即：**排序**比**绝对打分**容易得多

### 5.4 两个新漏洞

| 漏洞 | 表现 | 对约师的风险 |
|---|---|---|
| **prompt 复杂度敏感** | prompt 越复杂，评委越不稳 | 我们的 rubric prompt 很复杂（4 维度 × 5 档 + 证据链） |
| **宽松偏差（leniency）** | 评委倾向给更高（更宽松）的分数 | 会抬高老师分数 → "通过"太多，准入门失守 |

---

## 6. 对本项目的作用

### 6.1 补充新 bias：宽松偏差

zheng-2023 讲了位置 / 长度 / 自我偏好三种 bias；这篇补上**宽松偏差**——LLM 评委偏于给高分。但这不会影响到教师之间的相对分数，因为都“宽松”。

### 6.2 警示：rubric prompt 太复杂

需考虑**简化 prompt 或拆分评分**（如每维度单独一调用）来换取稳定性。

### 6.3 度量陷阱 → 呼应 NFR-Q1

论文强调"百分比一致率不够"。你的 NFR-Q1 已用 **ICC / Kappa**，方向正确；但要注意，如果将来有人用"一致率 90%+"来汇报评分质量，要警惕那是**虚高**的指标。

### 6.4 总体警示

"即使在相当干净的实验设置里，最好的评委也和人类有偏差" → 复杂真实场景（如教学能力评估）要更谨慎。**AI 评分只能做初筛，最终准入必须有人工兜底**。

---

## 7. 关键启示

1. **只有大模型勉强可信**，且仍差 5 分——别指望 AI 一次评准。
2. **宽松偏差会放大"通过"**：LLM 偏高分 → 准入门失守 → 必须结果分级 + 人工复核。
3. **prompt 越复杂，评委越不稳**：rubric prompt 要克制复杂度，必要时拆分评分。
4. **别用百分比一致率自欺**：用 ICC / Kappa（呼应 NFR-Q1）。
