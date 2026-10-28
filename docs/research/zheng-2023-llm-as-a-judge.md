# Zheng et al. (2023) — Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena 文献精读

> 定位：本项目"用 LLM 按 rubric 打分"可行性的**实证依据**，也是评分 bias 防治的参考

---

## 1. 文献信息

| 项 | 内容 |
|---|---|
| 标题 | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena |
| 作者 | Lianmin Zheng, Wei-Lin Chiang, Ying Sheng, Siyuan Zhuang, Zhanghao Wu, Yonghao Zhuang, Zi Lin, Zhuohan Li, Dacheng Li, Eric P. Xing, Hao Zhang, Joseph E. Gonzalez, Ion Stoica |
| 会议 | NeurIPS 2023（Datasets and Benchmarks Track） |
| 机构 | UC Berkeley（LMSYS Org） |
| 类型 | 基准 / 实证论文 |
| 关键词 | LLM-as-a-Judge、MT-Bench、Chatbot Arena、Elo rating、位置 bias、长度 bias、自我偏好 bias |

> 原文：arXiv [2306.05685](https://arxiv.org/abs/2306.05685)

---

## 2. 一句话概括

用 LLM 给另一个 LLM 打分（**LLM-as-a-judge**）这件事，能不能被信任？作者做了两个东西来回答——**MT-Bench**（80 题多轮基准）+ **Chatbot Arena**（众包投票平台）——结论是：**强 LLM 当评委能达到人类水平（一致率 >80%），但有位置、长度、自我偏好三种 bias 要防**。

---

## 3. 核心问题

1. LLM 当"评委"给其他模型的回答打分，可靠吗？和人类打分差多少？
2. LLM 评委有哪些系统性 bias？
3. 怎么量化地"评判评委本身"？

---

## 4. 两个贡献：MT-Bench 与 Chatbot Arena

### 4.1 MT-Bench：给评委的"考卷"

- **80 道多轮题**，覆盖 8 类（写作、角色扮演、抽取、推理、数学、编程、STEM、人文社科）
- 每题配**专家写的参考答案**（reference answer）
- 用 LLM 评委打分，再和人类专家打分**比对**

### 4.2 Chatbot Arena：众包"擂台"

- 用户和两个**匿名**模型对话，投票"哪个更好"
- 用 **Elo 评分**（Bradley-Terry 模型）给模型排序
- 规模：约 3 万投票、覆盖数十个模型

---

## 5. 关键发现

### 5.1 LLM-as-a-judge 可行

- GPT-4 评委与人类专家的一致率 **>80%**，接近**人类-人类之间的一致率（~81%）**
- **多轮 + 有参考答案**时，LLM 评委更稳定

### 5.2 但有三种 bias

| bias | 表现 | 对我们的意义 |
|---|---|---|
| **位置 bias** | 偏好排在某个位置的答案（常是第一个） | 多轮答辩里，轮次顺序可能影响打分 |
| **长度 bias** | 偏好更长的答案 | 讲得啰嗦的人可能被评更高 |
| **自我偏好 bias** | 偏好自己 / 同源模型生成的答案 | 若用同一模型生成"参考答案"再评分，有自我偏好评风险 |

### 5.3 推理能力有限

- 在数学 / 推理题上，LLM 评委容易被绕晕、评分不稳

---

## 6. 对本项目的作用

### 6.1 正面：验证"LLM 按 rubric 打分"可行

一致率 >80% 接近人类-人类水平 → 支持我们用 LLM 评分（对应 NFR-Q1）。

### 6.2 警示：三种 bias 要防

- **长度 bias**：rubric 里"表达清晰度"档位明确写了"简洁准确"，但仍要警惕 LLM 给啰嗦的长讲题打高分——需在 prompt 里**显式约束"不以长度论好坏"**
- **位置 bias**：多轮答辩中可能偏好某轮的回答——评分应**按维度找证据，而非按轮次线性评**
- **自我偏好**：若未来用 LLM 生成"参考讲题"再让同源模型评，有自我偏好风险

### 6.3 方法借鉴：给"参考答案"和 rubric

MT-Bench 的关键是**每题配专家参考答案**。对应到我们：情景卡的「评分要点 + 常见偏差」就是"参考答案 + 干扰项"，这正是让 LLM 评委变稳的关键。

### 6.4 推理短板 → 数学题要人工兜底

论文发现 LLM 在数学 / 推理上评分不稳。约师已把「学科准确性」移出范围（默认教师已掌握），但**讲错仍要在讲解逻辑/表达清晰度上扣分**——LLM 能不能可靠地"发现讲错"，正是这个短板。

---

## 7. 关键启示

1. **LLM 评分可行**：一致率 >80% 接近人类水平，方向成立。
2. **三种 bias 必须防**：位置、长度、自我偏好——都要写进评分 prompt 的约束。
3. **参考答案是稳定器**：rubric + 评分要点 + 常见偏差 = 我们的"参考答案"，是评分稳定的关键。
4. **数学判断是 LLM 短板**：学科准确性虽已移出范围，但"判断讲错"仍依赖 LLM 的数学能力，需人工抽检兜底。
