"""
LLM 客户端：OpenAI 兼容接口 + dry-run 桩模式。

设计要点:
  * 每次调用都是全新 messages，不共享历史（保证 3 次采样相互独立）；
  * dry_run=True 时返回与真实结构一致的桩数据，便于无密钥跑通全链路；
  * 调用失败重试 3 次后抛出，由上层决定是否中断。
"""
import json
import time

from .config import config

try:
    from openai import OpenAI
except ImportError:  # 允许无 openai 依赖时以 dry-run 运行
    OpenAI = None


class LLMError(RuntimeError):
    """LLM 调用失败（重试后）。"""


class LLMClient:
    """OpenAI 兼容客户端封装。"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.model = config["llm"]["model"]
        self.base_url = config["llm"]["base_url"]
        self.api_key = config["llm"]["api_key"]
        self.calls = 0          # 累计调用次数
        self.tokens = 0         # 累计 token（真实调用时由接口返回）
        self._client = None
        if not dry_run:
            if OpenAI is None:
                raise LLMError("未安装 openai，请 pip install openai 或使用 --dry-run")
            if not self.api_key:
                raise LLMError("缺少 LLM_API_KEY，请在 .env 中配置或使用 --dry-run")
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    # ---------- 主入口 ----------

    def chat(self, prompt: str, temperature: float = 0.5, task: str = "default") -> str:
        """
        发送单轮 prompt，返回文本。

        Args:
            prompt: 完整提示词（system 与 user 已合并；本流程无多轮对话）
            temperature: 采样温度
            task: 任务标识，dry-run 下据此返回对应桩数据
        Returns:
            模型输出文本
        """
        if self.dry_run:
            return _stub(task)

        last_error = None
        for attempt in range(3):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                self.calls += 1
                if resp.usage:
                    self.tokens += resp.usage.total_tokens
                return resp.choices[0].message.content or ""
            except Exception as exc:            # noqa: BLE001 网络/配额等均重试
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"LLM 调用失败：{last_error}")

    def chat_json(self, prompt: str, temperature: float = 0.5, task: str = "default") -> dict:
        """
        要求模型返回 JSON 并解析。容忍 ```json 代码块包裹。
        解析失败会重试一次（换更严格的指令）。
        """
        text = self.chat(prompt, temperature=temperature, task=task)
        data = _extract_json(text)
        if data is not None:
            return data

        retry_prompt = prompt + "\n\n注意：只输出 JSON 对象，不要任何解释文字、不要 Markdown 代码块。"
        text = self.chat(retry_prompt, temperature=0.0, task=task)
        data = _extract_json(text)
        if data is None:
            raise LLMError(f"模型输出无法解析为 JSON：{text[:200]}")
        return data

    def stats(self) -> dict:
        return {"calls": self.calls, "tokens": self.tokens, "dry_run": self.dry_run}


def _extract_json(text: str):
    """从模型输出中提取第一个 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- dry-run 桩

_DRY_QA = {
    "questions": [
        {
            "round": 1,
            "persona_id": "P1",
            "persona_name": "概念严谨型",
            "text": "老师，您说科学记数法要写成 A×10ⁿ，其中 A 比 10 小、比 1 大。"
                    "但课本例 5（1）是 1×10⁶，这里的 1 并不比 1 大。定义是不是应该写成 1≤A<10？",
            "reference_points": [
                "指出原表述应为 1≤A<10",
                "承认表述不够严谨并修正",
                "说明 A=1 时合规",
            ],
        },
        {
            "round": 2,
            "persona_id": "P2",
            "persona_name": "基础困惑型",
            "text": "老师，3 后面有 8 个 0，为什么是 3×10⁸，不是 30×10⁷？10⁸ 到底表示 1 后面几个 0？",
            "reference_points": [
                "解释 10⁸ 表示 1 后面 8 个 0",
                "说明 A 必须落在 1~10 之间，所以取 3 不取 30",
                "用具体数字逐步演示",
            ],
        },
        {
            "round": 3,
            "persona_id": "P4",
            "persona_name": "拓展挑战型",
            "text": "老师，比 100 万大的数可以用科学记数法，那像 -300000000 这样的负数能不能写成 -3×10⁸？",
            "reference_points": [
                "说明负数也可以，符号保留在 A 前",
                "指出初中阶段主要研究大于 10 的正数",
                "不过度延伸到未学的负指数",
            ],
        },
    ]
}

_DRY_GENERAL = {
    "dimensions": [
        {
            "dimension": "G1",
            "name": "教学目标与设计",
            "score": 4,
            "rationale": "导入、新授、练习、小结四个环节齐全，且围绕「理解并会用科学记数法」展开；"
                         "导入用真实数据切入，指向明确。扣分点：未在开课时明确「学完能做到什么」。",
            "evidence": "带着这个问题，让我们开始本节课的学习——《科学记数法》。",
        },
        {
            "dimension": "G2",
            "name": "教学内容与学科素养",
            "score": 3,
            "rationale": "讲清了操作步骤，但对「为什么要把 A 限定在 1≤A<10」的必要性解释不足，"
                         "停留在「规则是什么」，未触及「为什么这样规定」，学科思想体现较弱。",
            "evidence": "对于 A 而言要比 10 小、比 1 大。",
        },
        {
            "dimension": "G3",
            "name": "教学实施与方法",
            "score": 4,
            "rationale": "语言清晰、有提问和候答，并组织了小组讨论；但理答多为简单肯定，"
                         "缺少对错误的追问与深挖。",
            "evidence": "观察的很仔细，总结的很全面，请坐。",
        },
    ]
}

_DRY_CHECKPOINT = {
    "checkpoints": [
        {"checkpoint_id": "CP-1", "status": "覆盖", "evidence": "这些大的数据不仅读起来费劲，写起来也很麻烦"},
        {"checkpoint_id": "CP-2", "status": "覆盖", "evidence": "根据有理数的乘方运算……10²=100，10³=1000"},
        {"checkpoint_id": "CP-3", "status": "覆盖", "evidence": "乘方可以表示出特别大的数，而且书写形式也比较简单"},
        {"checkpoint_id": "CP-4", "status": "覆盖", "evidence": "3 后面有 8 个 0，所以应该是 3×10⁸"},
        {"checkpoint_id": "CP-5", "status": "覆盖", "evidence": "第三小组的代表说：这几个数字都是用一个数和 10ⁿ 相乘表示的"},
        {"checkpoint_id": "CP-6", "status": "覆盖", "evidence": "对于 A 而言要比 10 小、比 1 大"},
        {"checkpoint_id": "CP-7", "status": "部分覆盖", "evidence": "只给出例 5 答案，未讲「n = 整数位数 − 1」的方法"},
        {"checkpoint_id": "CP-8", "status": "覆盖", "evidence": "你说学习了科学记数法，知道了……注意的项"},
    ]
}

_DRY_QA_SCORE = {
    "rounds": [
        {
            "round": 1,
            "scores": [
                {"dimension": "Q1", "name": "应答切题", "score": 4,
                 "rationale": "正面承认问题并给出修正", "evidence": "科学记数法的定义应该是 1≤A<10"},
                {"dimension": "Q2", "name": "因材施教", "score": 4,
                 "rationale": "给出了严谨的边界表述，符合该学生类型期待", "evidence": "你观察得很仔细"},
                {"dimension": "Q3", "name": "启发引导", "score": 3,
                 "rationale": "直接给出正确答案，未引导该学生自己发现「1 是否合规」", "evidence": "A 可以等于 1"},
            ],
        },
        {
            "round": 2,
            "scores": [
                {"dimension": "Q1", "name": "应答切题", "score": 4,
                 "rationale": "解答了 10⁸ 的含义与 A 的取值范围", "evidence": "10⁸ 表示 1 后面有 8 个 0"},
                {"dimension": "Q2", "name": "因材施教", "score": 4,
                 "rationale": "用具体数字拆解，贴合基础薄弱学生", "evidence": "从右边数一共有 9 位数"},
                {"dimension": "Q3", "name": "启发引导", "score": 3,
                 "rationale": "以讲解为主，较少反问让学生自己数", "evidence": "你可以自己数一数"},
            ],
        },
        {
            "round": 3,
            "scores": [
                {"dimension": "Q1", "name": "应答切题", "score": 4,
                 "rationale": "明确回答了负数可否使用", "evidence": "负数也可以用科学记数法"},
                {"dimension": "Q2", "name": "因材施教", "score": 3,
                 "rationale": "延伸了负数情形，但对「不超纲」的边界交代略简", "evidence": "会涉及负指数"},
                {"dimension": "Q3", "name": "启发引导", "score": 4,
                 "rationale": "点到为止并说明后续内容，处理得当", "evidence": "那是你们以后要学的内容"},
            ],
        },
    ]
}

_DRY_SUGGESTIONS = {
    "suggestions": [
        {"target": "讲稿", "text": "补上「为什么」：在得出 1≤A<10 后，说明这一规定的意义（统一写法便于比较大小、便于科学计算），而不只是「规则如此」。"},
        {"target": "讲稿", "text": "例 5 不只给答案，明确「n = 整数位数 − 1」这一方法，并用 696×10³ 说明违规。"},
        {"target": "讲稿", "text": "学生答对时追问「为什么这样想」，把简单肯定升级为理解性反馈。"},
        {"target": "问答", "text": "第 1 轮可改为反问「例 5 里的 1，满不满足『比 1 大』？」，让学生自己发现表述漏洞。"},
        {"target": "问答", "text": "第 3 轮注意不超纲：学生问到负数时点到为止，避免引入未学的负指数概念。"},
    ]
}


def _stub(task: str) -> str:
    """dry-run 桩数据：与真实调用返回同样的 JSON 结构。"""
    mapping = {
        "qa_generation": _DRY_QA,
        "score_general": _DRY_GENERAL,
        "score_checkpoint": _DRY_CHECKPOINT,
        "score_qa": _DRY_QA_SCORE,
        "suggestions": _DRY_SUGGESTIONS,
    }
    return json.dumps(mapping.get(task, {}), ensure_ascii=False)