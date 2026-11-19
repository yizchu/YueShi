# 系统部署

> 文档定位：从零把 EduEval 跑起来（本地或内网服务器），以及对外提供服务时的注意事项。
> 面向：部署者/运维；不含开发调试细节（见 [code_quality.md](code_quality.md)）。
> 配套：[architecture.md](architecture.md)（分层与单进程约束） · [design.md](design.md)（交互形态）

---

## 0. 部署形态一览

| 形态 | 入口 | 适用场景 | 是否需要 API Key |
|---|---|---|---|
| **CLI** | `python run.py run ...` | 研究者批量/单人本地评估 | 是（除 `--dry-run`） |
| **Web** | `python web.py --port 8000` | 被试在浏览器里作答 | 是（除无 key 自动降级） |
| 演示 | 任一入口 + `--dry-run` | 界面走查、培训、回归测试 | 否 |

系统**无数据库、无 Redis、无消息队列、无 GPU**。所有状态落在 `workspace/<sessionId>/session.json`，随时可删、可拷、可归档。

---

## 1. 环境要求

| 项 | 要求 | 说明 |
|---|---|---|
| Python | **3.10+**（开发与验证用 3.10.6） | 代码用了 `int \| None` 这类 3.10 语法 |
| 操作系统 | Windows 10/11 或 Linux（macOS 未测但应可用） | 关键路径无平台特定调用 |
| 内存 | ≥ 512 MB | 纯文本处理 |
| 网络 | 可访问 LLM 服务（默认 `api.deepseek.com`） | 无 key 时走 dry-run |
| 磁盘 | ≥ 200 MB（含依赖与若干会话） | 单次会话约 10~50 KB |

已验证的依赖版本：`openai 1.54.4`、`pyyaml 6.0`、`fastapi 0.115.12`、`uvicorn 0.26.0`。

---

## 2. 安装

```bash
# 1) 取代码（当前尚未纳入 git，直接拷贝 yueshi/ 目录即可）
cd yueshi/EduEval

# 2) 建虚拟环境（推荐，避免污染系统 Python）
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 3) 装依赖
pip install -r requirements.txt
# 或作为包安装（会带上 prompts 资源，便于从任意目录 import）
pip install -e .
```

`requirements.txt` 只有 4 个直接依赖：

```text
openai>=1.30,<2.0
pyyaml>=6.0
fastapi>=0.110
uvicorn>=0.26
```

跑测试再装 `pytest>=8.0`（`requirements.txt` 里是注释掉的，避免生产环境带入）。

---

## 3. 配置

### 3.1 密钥（`.env`）

在 `EduEval/` 下新建 `.env`（**不要提交**，`.gitignore` 已忽略）：

```ini
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `LLM_API_KEY` | 是（真实调用时） | 空 | 缺失时 CLI 与 Web 都自动降级为 dry-run 桩 |
| `LLM_BASE_URL` | 否 | `https://api.deepseek.com` | 任意 OpenAI 兼容端点均可 |
| `LLM_MODEL` | 否 | `deepseek-chat` | 需支持 JSON 输出与较长上下文（讲稿上限 8 000 字） |

### 3.2 运行参数（`config.yaml`）

代码内已给默认值，一般不需要改。可调项：

| 键 | 默认 | 含义 |
|---|---|---|
| `temperature.qa` | 0.8 | 提问生成温度（偏高，求多样） |
| `temperature.score` | 0.5 | 评分温度（偏低，求稳定） |
| `temperature.suggestion` | 0.7 | 建议生成温度 |
| `limits.min_script_words` | 300 | 讲稿字数下限（Web 返回 422） |
| `limits.min_answer_words` | 50 | 单轮回答字数下限 |
| `limits.max_script_words` | 8000 | 超长截断，报告会标注 |
| `qa.rounds` | 3 | 问答轮数（固定 3） |
| `qa.persona_count` | 3 | 从 5 类人设中抽 3 类 |
| `paths.datasets` / `paths.workspace` | `datasets` / `workspace` | 相对 `EduEval/` 的路径 |

配置在**进程启动时读一次**（`config.py:80` 的模块级 `config = _load_config()`）。CLI 每次运行都是新进程，改完即生效；Web 进程常驻，改 `config.yaml` 或 `.env` 后需要**重启服务**。

---

## 4. 运行

### 4.1 CLI

```bash
cd EduEval

# 看题库
python run.py list
python run.py list --json      # 机器可读

# 随机抽题 + 交互式问答（讲稿走文件，问答在终端）
python run.py run --lecture path/to/lecture.md

# 复现某道题（跳过随机抽题）
python run.py run -q M-CZ-001 --lecture path/to/lecture.md

# 演示/回归：不调模型
python run.py run --lecture datasets/examples/M-CZ-001-高质量讲稿.md --dry-run --out out/demo

# 非交互：答案一次性给（批量评测的基础）
python run.py run -q M-CZ-001 -l lecture.md -a answers.json --dry-run

# 续跑（终端意外中断后）
python run.py run --session workspace/EV-20261118-210301
```

参数速查：`-q/--question`、`-l/--lecture`、`-a/--answers`、`-s/--session`、`-o/--out`、`--dry-run`、`--seed`、`--candidate`。

退出码：`0` 成功；非 0 表示讲稿不合法、LLM 失败或参数错误（终端有中文原因）。

### 4.2 Web

```bash
cd EduEval

# 开发/内网
python web.py --port 8000

# 显式指定监听地址（对外）
python web.py --host 0.0.0.0 --port 8000

# 或直接交给 uvicorn（生产建议显式 --workers 1）
uvicorn web:app --host 0.0.0.0 --port 8000 --workers 1
```

打开 `http://<host>:8000/` 即进入三屏流程：抽题 → 讲稿 → 逐轮问答 → 报告。

接口（便于反向代理与健康检查）：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 健康检查，返回 `{"status": "ok"}` |
| GET | `/api/config` | 前端读取：模型名、是否有 key、轮数、字数下限 |
| GET | `/api/questions` | 题库列表（不含采分点） |
| GET | `/api/draw` | 随机抽 1 题（系统抽题，被试不能自选） |
| POST | `/api/sessions` | 建会话（可带 `dryRun`） |
| GET | `/api/sessions/{id}` | 会话详情（未揭示的问题文本为空串） |
| POST | `/api/sessions/{id}/answers` | 提交一轮回答（必须按序） |
| POST | `/api/sessions/{id}/score` | 评分（幂等，已评直接回放） |
| GET | `/api/sessions/{id}/report.md` | 下载 Markdown 报告 |

---

## 5. 数据目录与备份

```text
EduEval/
├── datasets/                  # 题目、人设、示例（人工维护，纳入备份）
│   ├── questions/*.json
│   ├── personas/personas.json
│   └── examples/
├── workspace/                 # 运行时产物（可随时清理）
│   └── EV-20261118-210301/
│       ├── lecture.md
│       ├── session.json       # 单一事实源
│       └── report.md
└── results/                   # 批量评测输出（当前仅占位）
```

- **要备份**：`datasets/` + `edu_eval/prompts/`（评分标准与规则）。
- **不必备份**：`workspace/`、`results/`、`.venv/`、`__pycache__/`。
- **归档**：把 `workspace/<id>/session.json` 与 `report.md` 一起拷走即可完整复现一次评估（含讲稿与三问三答）。
- **清理**：`workspace/` 按会话 ID 命名，直接删过期目录；注意删除后 Web 端还有效的会话链接会 404。

---

## 6. 对外提供服务的注意事项

这一节是**硬约束**，违反会出问题：

1. **只能单进程**（`--workers 1`）。会话状态在进程内存，多 worker 会各持一份、互相看不见。
2. **无鉴权、无账号**。页面与接口对任何能访问端口的人开放。对外必须放在反向代理（Nginx/Caddy）后面，加 TLS + IP 白名单或 Basic Auth。
3. **配额与限流**。一次评估会调 4~5 次 LLM（3 问生成 1 次、三块评分 3 次、建议 1 次），单次成本约 ¥0.1~0.5。建议在反代层按 IP 限速，避免被刷。
4. **请求体上限**。讲稿上限 8 000 字，反代 `client_max_body_size` 设 1 MB 足够。
5. **超时**。评分是同步调用，模型慢时单请求可能 30~60 s；反代 `proxy_read_timeout` 建议 ≥ 120 s。
6. **会话目录权限**。`workspace/` 含被试讲稿（个人信息），不要通过静态服务器暴露；`web.py` 只按 ID 返回 JSON/Markdown，不暴露目录列表。

最小反代片段（Caddy）：

```text
eval.example.com {
    reverse_proxy 127.0.0.1:8000
    basicauth / * {
        admin $2a$14$...
    }
}
```

（`basicauth` 的密码哈希用 `caddy hash-password` 生成。）

---

## 7. 排障

| 现象 | 原因 | 处理 |
|---|---|---|
| 启动即提示「未配置 API Key，已进入 dry-run」 | 缺 `.env` 或变量名写错 | 检查 `LLM_API_KEY`；只演示则忽略 |
| `UnicodeEncodeError: 'gbk' codec can't encode '\u2713'` | Windows 控制台/重定向编码 | 已由 `_ensure_utf8_stdout()` 处理；若仍出现，设 `PYTHONIOENCODING=utf-8` |
| `ModuleNotFoundError: edu_eval` | 不在 `EduEval/` 下运行 | `cd EduEval` 后再跑，或 `pip install -e .` |
| 端口被占用（`[Errno 10048]`） | 上一个 uvicorn 未退 | `netstat -ano \| findstr :8000` 找到 PID 后结束；或换 `--port 8001` |
| Web 提交回答返回 409 | 跳轮或重复提交 | 按提示先答完前一轮；已评分的会话不再接受作答 |
| 评分返回 502/503 | LLM 调用失败/未配 key | 看服务端日志的错误消息；确认网络与配额 |
| 报告里公式显示成 `10^5` | 旧版本生成的报告 | 重新评分生成；当前版本已统一转 Unicode 上标 |
| 会话「消失」 | 换了机器/目录，或 `workspace/` 被清 | 拷回 `workspace/<id>/` 即可，Web 重启后按 ID 恢复 |

日志：CLI 直接打印到 stdout/stderr；Web 用 uvicorn 默认访问日志，业务错误在响应 `detail` 里。当前无文件日志与结构化日志（见需求规格 NFR-O 的未实现项）。

---

## 8. 升级与回滚

- **代码升级**：替换 `EduEval/` 代码 → `pip install -r requirements.txt` → 重启进程。`session.json` 只增字段，旧会话可继续用。
- **提示词升级**（`edu_eval/prompts/*.md`）：属于行为变更，需同步 `llm._stub()` 与测试；升级前用 `--dry-run` + 3 份真实样本对比报告差异。
- **回滚**：代码与提示词都在同一目录，保留上一版目录副本即可；`workspace/` 与版本无关，不需要回滚。
- **不建议**在生产机上直接改 `config.yaml` 的 `qa.rounds`：报告结构、前端轮次展示、测试断言都按 3 轮写死。

---

## 9. 部署后冒烟清单

```bash
cd EduEval

# 1) 静态与测试
python -m ruff check edu_eval web.py run.py setup.py tests
python -m pytest -q                      # 期望 36 passed

# 2) 无网络也能跑通
python run.py run --lecture datasets/examples/M-CZ-001-高质量讲稿.md --dry-run --out "%TEMP%\ev_smoke"
# 期望：退出码 0，输出目录下有 report.md，报告评级「合格」

# 3) Web 起来了
python web.py --port 8000 &
curl http://127.0.0.1:8000/api/health     # {"status":"ok"}
curl http://127.0.0.1:8000/api/config     # 看到 model / hasKey / rounds
```

全部通过即视为部署成功。真实模型链路需在配好 key 后另跑一次：`python run.py run --lecture ... --out out/real`，并人工检查报告里的证据引用是否指向讲稿原文。