# 开源技术选型与拼接方案（简化版）

> 配套文档：[`README.md`](../README.md)
> 前提：采纳 [README 3.1](../README.md) 的简化方案——**异步多轮 + 文本疑问 + 音频为主**

## 1. 自研 vs 拼接的边界

**只有两样东西需要自研：**

1. **评分 rubric**（附录 A 的 5 维度 × 5 档量表）
2. **情景题库**（`docs/scenario-cards.md`）

**其余全部拼接开源件。** 这也是护城河所在——模型今天用 Qwen、明天可以换 GLM，但 rubric 和题库是你自己的。

## 2. 简化后：保留什么、砍掉什么

| | 组件 |
|---|---|
| ✅ **第一版保留** | ASR 转写、VAD、语音特征、LLM 评分、人工复核、流程编排 |
| ❌ **第一版砍掉** | 实时语音框架、TTS（语音合成）、端到端语音模型、WebRTC 实时通道、多模态评课 |

砍掉的这些原本是"AI 虚拟学生实时对话"的配套，改成**文本疑问异步呈现**后全部不再需要。

## 3. 第一阶段选型（必装）

| 环节 | 开源件 | 许可证 | 备注 |
|---|---|---|---|
| 音频转码 / 切分 | FFmpeg | LGPL-2.1+ | 注意不要启用 GPL 组件 |
| **语音转写 ASR** | [FunASR](https://huggingface.co/funasr/paraformer-zh)（Paraformer / SenseVoice） | MIT（模型多为 Apache-2.0） | 中文更强；SenseVoice 自带情感与音频事件检测 |
| ASR 备选 | faster-whisper | MIT | 多语言、生态成熟 |
| 词级时间戳 | WhisperX | BSD-2 | 语速 / 停顿 / 口头禅分析的基础 |
| 静音与停顿检测 | Silero VAD | MIT | CPU 可跑 |
| 韵律特征 | librosa | ISC | 语速、基频、能量 |
| **LLM 评分** | Qwen / GLM / DeepSeek | Apache-2.0 等 | 先走 API，省去 GPU |
| LLM 本地推理 | vLLM / SGLang / Ollama | Apache-2.0 / MIT | 需要自建算力时用 |
| 流程编排 | LangGraph 或自研脚本 | MIT | 第一版脚本足够 |
| **人工复核后台** | Label Studio | Apache-2.0 | 直接当复核后台，顺带沉淀标注数据 |
| 评分质量评测 | DeepEval / promptfoo | Apache-2.0 / MIT | 测 AI 分与人工分的一致性 |

**部署形态**：全 CPU 可跑通（ASR 用轻量模型 + LLM 走 API），**不需要 GPU**。

## 4. 第二阶段选型（升级项）

| 环节 | 开源件 | 许可证 | 用途 |
|---|---|---|---|
| 多模态评课 | Qwen2.5-VL / InternVL | Apache-2.0 | 分析表情、板书，检测念稿 |
| 视线估计 | MediaPipe + OpenCV | Apache-2.0 | 是否看镜头、念稿检测 |
| 声纹核验 | 3D-Speaker / WeSpeaker / SpeechBrain | Apache-2.0 | 确认本人试讲 |
| 实时语音对话 | Pipecat / LiveKit Agents | BSD-2 / Apache-2.0 | 仅在需要实时交互时引入 |
| 语音合成 TTS | CosyVoice / GPT-SoVITS | Apache-2.0 / MIT | 为"虚拟学生"配音 |
| 端到端语音模型 | Qwen2.5-Omni / Moshi | Apache-2.0 | 低延迟对话的备选路线 |

## 5. ⚠️ 许可证雷区（商用必查）

| 项目 | 许可证 | 问题 |
|---|---|---|
| Fish-Speech | CC-BY-NC-SA | **禁止商用** |
| ChatTTS | AGPL-3.0 | 传染性强，商用需谨慎 |
| [InsightFace 预训练模型](https://www.insightface.ai/zh/solutions/face-recognition-licensing) | 部分非商用 | 需购买企业授权 |
| praat-parselmouth | GPL-3.0 | 传染性强 |
| FFmpeg | LGPL / GPL | 启用 GPL 组件后分发受限 |

**建议**：选型表以"许可证"为硬性门槛，优先选 MIT / Apache-2.0 / BSD，别等上线前才发现问题。

## 6. 合规提醒

- 若 AI 评分对外提供服务，可能涉及**生成式人工智能服务备案**
- 试讲场景涉及未成年人的相关信息，需按个人信息保护要求处理
- 试讲音视频需取得试讲者**肖像与录音授权**
- AI 评分结果应**可申诉、可复评**，并给出评分理由

## 7. 一句话总结

**需要自研的是"评什么"（rubric + 题库），开源件解决"怎么评"（转写 + 打分 + 复核）。**
简化掉实时语音后，第一版的技术栈收敛为一个后端 + 一个录播前端 + 一条评分脚本，全 CPU 可跑。
