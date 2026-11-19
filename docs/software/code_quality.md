# 代码质量

> 文档定位：说明本项目的质量目标、编码约定、当前实际度量与已知质量债。
> 面向：维护代码的人（含未来的自己）。
> 配套：[architecture.md](architecture.md)（分层与模块职责） · [code_review.md](code_review.md)（缺陷与评审记录）

---

## 0. 范围

本文覆盖 `EduEval/` 下的全部实现代码：

| 路径 | 类型 | 说明 |
|---|---|---|
| `edu_eval/` | 包（10 个模块） | 核心逻辑：加载、编排、生成、评分、报告 |
| `web.py` | 单文件服务 | FastAPI 薄包装，复用 `edu_eval` 全部逻辑 |
| `run.py` | 入口 | 等价于 `python -m edu_eval` |
| `tests/` | 测试 | `test_core.py`（25 项）+ `test_web.py`（8 项） |
| `static/` | 前端 | 原生 HTML/CSS/JS，无构建、无框架 |

不在本文范围：`datasets/`（数据资产）、`docs/`（文档）、`workspace/`（运行时产物）。

---

## 1. 质量目标

按重要性排序，全部可度量：

| 目标 | 衡量方式 | 当前状态 |
|---|---|---|
| **行为正确** | 自动化测试全绿 | 36 passed |
| **可运行** | `compileall` 无错、dry-run 全链路出报告 | 通过（≈5 s） |
| **静态干净** | `ruff check` 零告警（默认 E/F 规则） | 0 findings（ruff 0.11.2） |
| **可读** | 模块/函数中文 docstring、公共签名类型标注 | 100% 覆盖 |
| **可复现** | `--seed` 固定人设与桩数据；`--dry-run` 不依赖网络 | 支持 |
| **依赖克制** | 运行时依赖 ≤ 4 个直接依赖 | openai / pyyaml / fastapi / uvicorn |

刻意**不追求**：类型检查全绿（未引入 mypy）、测试覆盖率百分数、微服务化、前端工程化。理由见 §5。

---

## 2. 编码约定

| 维度 | 约定 | 示例 |
|---|---|---|
| 模块 docstring | 第一行说清职责；有必要时补「为什么这么做」 | `reporter.py` 首行「报告生成：把评分结果拼装成 Markdown」 |
| 函数 docstring | 公共函数写 Args/Returns；简单函数一句话 | `assets.draw_question` 写明「题库为空抛 FileNotFoundError」 |
| 类型标注 | 公共函数签名全标注（含返回）；argparse 参数显式 `type=` | `def draw_question(seed: int \| None = None) -> Question` |
| 私有性 | 模块内部辅助一律 `_` 前缀 | `_resume`、`_save_progress`、`_extract_json` |
| 异常 | 不静默吞异常；错误消息带可操作信息 | `RuntimeError("问题生成失败：未返回有效问题")` |
| 容错 | 仅对**外部输入**做兜底，且注释说明 | `llm.py:70` 读 `.env` 失败时的 `except Exception: pass` |
| 常量 | 模块级 UPPER_CASE，就近定义 | `STATUS_ICON`、`_EXPONENT`、`_TOPIC_GROUPS` |
| 提示词 | 业务规则放 `prompts/*.md`，代码只做填充与解析 | `fill()` 而非 `str.format()`（模板含 JSON 花括号） |
| 报告 | 直接拼 Markdown 字符串，不用模板引擎 | `reporter.render_report` |
| Web | 只做协议转换：参数校验 → 调核心模块 → 组响应 | `web.py` 不重写评分逻辑 |

**依赖边界**（重要）：`web.py` 允许 import `edu_eval`；`edu_eval` 任何模块**不允许** import `web`。这条保证 CLI 在无 FastAPI 环境下也能跑。

---

## 3. 当前度量

实现代码合计 **2 460 行**（不含测试与前端），100 个函数、15 个类。

| 文件 | 行数 | 函数 | 类 | 职责 |
|---|---:|---:|---:|---|
| `web.py` | 547 | 21 | 3 | HTTP 接口 + 内存会话 |
| `edu_eval/__main__.py` | 476 | 14 | 0 | CLI 命令与交互问答 |
| `edu_eval/scorer.py` | 263 | 12 | 0 | 三层评分 + 评级合成 |
| `edu_eval/llm.py` | 255 | 6 | 2 | 客户端、JSON 提取、dry-run 桩 |
| `edu_eval/reporter.py` | 218 | 13 | 0 | Markdown 报告拼装 |
| `edu_eval/qa_gen.py` | 153 | 7 | 0 | 人设抽取 + 3 问生成 + 去重 |
| `edu_eval/models.py` | 124 | 6 | 9 | dataclass 模型 |
| `edu_eval/assets.py` | 122 | 9 | 0 | 题库/人设/提示词加载 |
| `edu_eval/config.py` | 89 | 4 | 0 | 配置合并 + .env |
| `edu_eval/logs.py` | 81 | 4 | 1 | 日志初始化（stderr、幂等） |
| `edu_eval/mathfmt.py` | 69 | 4 | 0 | `^` → Unicode 上标 |
| `edu_eval/__init__.py` | 35 | 0 | 0 | 再导出 |
| `run.py` / `setup.py` | 13 / 15 | 0 | 0 | 入口与打包 |

函数长度分布：**5 / 100** 个函数超过 40 行。

| 行数 | 位置 | 函数 | 评价 |
|---:|---|---|---|
| 134 | `edu_eval/__main__.py:113` | `cmd_run` | 偏长，见质量债 P1 |
| 57 | `web.py:448` | `api_score` | 可接受（线性流程） |
| 46 | `web.py:359` | `api_create_session` | 可接受 |
| 45 | `edu_eval/qa_gen.py:58` | `generate_questions` | 重试循环，可接受 |
| 42 | `web.py:102` | `_load_session` | 可接受（反序列化样板） |

行宽：最长一行 101 字符（`qa_gen.py:54`），其余均 ≤ 100。

---

## 4. 自动化检查

```bash
cd EduEval

# 1) 静态检查（默认 E/F 规则集：语法错误、未使用导入/变量、f-string 问题）
python -m ruff check edu_eval web.py run.py setup.py tests

# 2) 可编译性
python -m compileall -q edu_eval web.py run.py tests

# 3) 单元测试（全 dry-run，不联网）
python -m pytest -q
```

当前输出：

| 检查 | 结果 |
|---|---|
| `ruff check` | `All checks passed!` |
| `compileall` | 无输出（成功） |
| `pytest -q` | `36 passed, 1 warning in ~3s` |

那 1 条 warning 来自第三方 `starlette/formparsers.py` 的 `PendingDeprecationWarning`，与本项目代码无关，不处理。

**测试覆盖的实际内容**（按组）：

| 组 | 覆盖点 |
|---|---|
| 资产 | 题库列举/读取、字段解析、人设加载、`fill()` 填充、随机抽题 |
| 模型 | dataclass 默认值、序列化字段 |
| LLM | `_extract_json` 容忍前后缀/非法输入 |
| 问答生成 | 人设抽取可复现、去重判定、3 问结构、参考要点存在性 |
| 评分 | 通用 3 项解析、采分点覆盖判定、门槛规则、评级边界（4.5 / 3.8 / 3.0） |
| 报告 | 章节齐全、`^` 归一化、表格竖线转义 |
| CLI | 端到端 dry-run、退出码、重定向输出编码 |
| Web | 建会话、逐轮揭示、跳轮 409、幂等评分、重启恢复、错误码 |

---

## 5. 已知质量债

| 级别 | 问题 | 位置 | 影响 | 计划 |
|---|---|---|---|---|
| **P1** | `cmd_run` 134 行，混合了「读讲稿/抽题/生成/问答/评分/落盘」六个阶段 | `edu_eval/__main__.py:113` | 改一处要通读全函数 | 抽出 `_stage_*` 小函数，或迁到 `pipeline.py` |
| **P1** | 无类型检查（mypy）与覆盖率统计 | 全仓 | 类型错只能靠运行期暴露 | 引入 mypy（先只查 `edu_eval`）；coverage 出报告后再定阈值 |
| **P1** | 提示词改动无回归测试 | `edu_eval/prompts/*.md` | 改 rubric 后只能靠跑一次真模型观察 | 用「固定模型输出样本 + 解析断言」做离线回归 |
| **P2** | `reference_points` 不校验非空 | `edu_eval/qa_gen.py:125` | 模型漏字段时问答评分失去锚点，且无提示 | 解析后断言非空，缺失则重试 |
| **P2** | 去重仅关键词组粗筛 | `edu_eval/qa_gen.py:35` | 语义重复可能漏判 | 与 N=3 采样一并做（见需求规格 P1） |
| **P2** | 无 CI（提交即跑三件套） | — | 依赖人工记得跑 | GitHub Actions / 本地 pre-commit |
| **P3** | 单行 101 字符 | `edu_eval/qa_gen.py:54` | 无 | 顺手折行 |
| **P3** | 数据与代码同仓，`workspace/` 会膨胀 | 仓库根 | 克隆变慢 | `workspace/` 已 gitignore；定期清理 |

---

## 6. 提交前检查清单

改完代码，按顺序跑一遍（约 10 秒）：

1. `python -m ruff check edu_eval web.py run.py setup.py tests` —— 必须 `All checks passed!`
2. `python -m compileall -q edu_eval web.py run.py tests` —— 必须无输出
3. `python -m pytest -q` —— 必须 `36 passed`
4. `python run.py run --lecture datasets/examples/M-CZ-001-高质量讲稿.md --dry-run --out %TEMP%\ev_smoke` —— 必须退出码 0 且生成 `report.md`
5. 若改了提示词：额外用 `--dry-run` 之外的真实调用跑一遍，人工读报告

前 3 条是硬门槛；第 4 条是冒烟；第 5 条只在动 `prompts/` 时要求。

---

## 7. 演进方向

按投入产出排序：

1. **拆 `cmd_run`**（P1，半天）：纯重构，有 36 项测试兜底，风险低。
2. **加 `mypy`**（P1，半天）：先 `--ignore-missing-imports` 只查 `edu_eval`，把 `Any` 收敛掉。
3. **提示词离线回归**（P1，1 天）：存 3 份真实模型输出 JSON 作 fixture，断言解析与评级稳定。
4. **`reference_points` 校验**（P2，1 小时）：解析后空列表即触发重试。
5. **CI**（P2，2 小时）：三件套 + dry-run 冒烟。

不建议现在做的：覆盖率阈值（样本太少，阈值会失真）、前端工程化（页面只有三屏）、微服务拆分（单体 2 300 行拆了只会增加沟通成本）。