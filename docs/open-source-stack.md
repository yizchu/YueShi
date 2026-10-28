# 开源技术选型与拼接方案（文本版）

> 配套文档：[project-plan.md](project-plan.md)
> 前提：**讲稿文本输入 + 多轮文本问答 + LLM 评分**，无音视频、无人工复核（人工复核属下游产业）。

---

## 1. 自研 vs 拼接的边界

**只有两样东西需要自研：**

1. **评分 rubric**（4 维度 × 5 档量表）
2. **题目题库**（`scenario-cards.md`）

**其余全部拼接开源件。** 这也是护城河所在——模型今天用 Qwen、明天可以换 GLM，但 rubric 和题库是你自己的。

---

## 2. 选型清单

| 环节 | 开源件 | 许可证 | 备注 |
|---|---|---|---|
| **LLM 评分** | Qwen / GLM / DeepSeek | Apache-2.0 等 | 先走 API，省去 GPU |
| LLM 本地推理 | vLLM / Ollama | Apache-2.0 / MIT | 需要自建算力时用 |
| 流程编排 | LangGraph 或自研脚本 | MIT | 第一版脚本足够 |
| 评分质量评测 | DeepEval / promptfoo | Apache-2.0 / MIT | 测评分一致性（ICC / Kappa） |
| 专家标注（研究用） | Label Studio | Apache-2.0 | 仅在研究验证阶段标注专家评分用 |

> 文本-only 后，**不再需要**：FFmpeg、ASR（FunASR/Whisper）、VAD、librosa、声纹核验、TTS、WebRTC 等音视频组件。

**部署形态**：走 LLM API + 一个后端脚本即可，**不需要 GPU**。

---

## 3. 许可证提醒

- 优先选 MIT / Apache-2.0 / BSD
- 音视频相关许可证雷区（Fish-Speech、ChatTTS、InsightFace 等）已随范围移除，不再相关

---

## 4. 合规提醒

- 若 AI 评分对外提供服务，可能涉及**生成式人工智能服务备案**
- 讲稿涉及个人信息，需按个人信息保护要求处理
- AI 评分结果应**可解释（附理由与证据）**，供下游产业自行开展人工复核

---

## 5. 一句话总结

**需要自研的是"评什么"（rubric + 题库），开源件解决"怎么评"（LLM 打分 + 评测）。**
文本-only 后，第一版技术栈收敛为**一个后端 + 一条评分脚本 + 一个 LLM API**，无需 GPU。
