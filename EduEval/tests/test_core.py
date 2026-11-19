"""
核心逻辑单元测试（不调用 LLM，用 dry-run 桩数据）。

运行:
    cd EduEval && python -m pytest tests/ -v
"""
import json
import re
import sys
from pathlib import Path

import pytest

from edu_eval.assets import load_question, load_personas, list_questions, fill
from edu_eval.llm import LLMClient, _extract_json
from edu_eval.mathfmt import normalize_math
from edu_eval.qa_gen import check_distinct, pick_personas, generate_questions
from edu_eval.models import (
    CheckpointResult,
    GeneratedQuestion,
    QAPair,
    Report,
    ScoreItem,
)
from edu_eval.reporter import render_report
from edu_eval.scorer import make_rating, _clamp

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- 资产

def test_list_questions():
    """题库至少有一道题，且必含科学计数法。"""
    questions = list_questions()
    assert len(questions) >= 1
    assert any(q.id == "M-CZ-001" for q in questions)


def test_load_question_fields():
    """题目字段完整：采分点数量与源 JSON 一致，核心采分点唯一且为 CP-6。"""
    q = load_question("M-CZ-001")
    assert q.title == "科学计数法"
    raw = json.loads((ROOT / "datasets/questions/M-CZ-001.json").read_text(encoding="utf-8-sig"))
    assert len(q.checkpoints) == len(raw["checkpoints"])
    assert len(q.core_checkpoints) == 1
    assert q.core_checkpoints[0].id == "CP-6"


def test_load_question_not_found():
    """不存在的题目要抛 FileNotFoundError 并提示可用 ID。"""
    with pytest.raises(FileNotFoundError) as exc:
        load_question("NOT-EXIST")
    assert "M-CZ-001" in str(exc.value)


def test_load_personas():
    """人设库 5 类。"""
    personas = load_personas()
    assert len(personas) == 5
    assert {p.name for p in personas} >= {"概念严谨型", "基础困惑型"}


def test_fill_tolerates_json_braces():
    """fill 不应被模板中的 JSON 花括号干扰。"""
    template = '示例：{"a": 1}，变量：{name}'
    assert fill(template, name="X") == '示例：{"a": 1}，变量：X'


# ---------------------------------------------------------------- 提问生成

def test_pick_personas_deterministic():
    """固定 seed 时抽取结果可复现。"""
    personas = load_personas()
    a = pick_personas(personas, 3, seed=42)
    b = pick_personas(personas, 3, seed=42)
    assert [p.id for p in a] == [p.id for p in b]


def test_pick_personas_no_duplicate():
    """抽取 3 类人设互不重复。"""
    personas = pick_personas(load_personas(), 3, seed=1)
    assert len({p.id for p in personas}) == 3


def test_check_distinct_pass():
    """考察点不同的 3 问应通过。"""
    qs = [
        GeneratedQuestion(1, "P1", "概念严谨型", "老师，A 的范围是 1≤A<10 吗？"),
        GeneratedQuestion(2, "P2", "基础困惑型", "老师，10⁸ 表示 1 后面几个 0？"),
        GeneratedQuestion(3, "P4", "拓展挑战型", "老师，负数能写成 -3×10⁸ 吗？"),
    ]
    ok, _ = check_distinct(qs)
    assert ok


def test_check_distinct_fail():
    """两问都问「范围」应判为重复。"""
    qs = [
        GeneratedQuestion(1, "P1", "概念严谨型", "老师，A 的范围是 1≤A<10 吗？"),
        GeneratedQuestion(2, "P2", "基础困惑型", "老师，A 的取值上限和下限是多少？"),
    ]
    ok, reason = check_distinct(qs)
    assert not ok
    assert "重叠" in reason


def test_generate_questions_dry_run():
    """dry-run 下能生成 3 问，且带参考应答要点。"""
    client = LLMClient(dry_run=True)
    q = load_question("M-CZ-001")
    questions = generate_questions(q, "这是一段测试讲稿" * 50, client, seed=7)
    assert len(questions) == 3
    assert all(gq.reference_points for gq in questions)
    assert [gq.round for gq in questions] == [1, 2, 3]


# ---------------------------------------------------------------- 评分

def test_clamp():
    """分数钳制在 1~5。"""
    assert _clamp(0) == 1
    assert _clamp(9) == 5
    assert _clamp("abc") == 1
    assert _clamp(3.4) == 3.4


def test_rating_good():
    """均分 4.0 且采分点全覆盖 → 良好。"""
    report = _make_report(general=[4, 4, 4], qa=[4, 4, 4], covered=9, missing_core=0)
    assert make_rating(report) == "良好"


def test_rating_excellent():
    """均分 4.7 → 优秀。"""
    report = _make_report(general=[5, 4, 5], qa=[5, 5, 4], covered=9, missing_core=0)
    assert make_rating(report) == "优秀"


def test_rating_pass():
    """均分 3.3 → 合格。"""
    report = _make_report(general=[3, 3, 4], qa=[3, 4, 3], covered=9, missing_core=0)
    assert make_rating(report) == "合格"


def test_rating_blocked_by_missing_core():
    """核心采分点缺失 → 即使高分也判待改进。"""
    report = _make_report(general=[5, 5, 5], qa=[5, 5, 5], covered=8, missing_core=1)
    assert make_rating(report) == "待改进"


def test_rating_blocked_by_low_coverage():
    """采分点覆盖不足半数 → 待改进。"""
    report = _make_report(general=[4, 4, 4], qa=[4, 4, 4], covered=3, missing_core=0)
    assert make_rating(report) == "待改进"


# ---------------------------------------------------------------- JSON 解析

def test_extract_json_plain():
    """纯 JSON 直接解析。"""
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_code_block():
    """容忍 ```json 代码块包裹。"""
    text = '```json\n{"a": 1}\n```'
    assert _extract_json(text) == {"a": 1}


def test_extract_json_with_prefix():
    """容忍 JSON 前后有多余文字。"""
    text = '好的，结果如下：{"a": 1} 以上。'
    assert _extract_json(text) == {"a": 1}


def test_extract_json_invalid():
    """非法 JSON 返回 None。"""
    assert _extract_json("这不是 JSON") is None


# ---------------------------------------------------------------- 辅助

def _make_report(general, qa, covered, missing_core) -> Report:
    """构造一个最小 Report 用于测试评级逻辑。"""
    q = load_question("M-CZ-001")
    report = Report(session_id="TEST", question=q, lecture="x" * 400)
    names = ["G1", "G2", "G3"]
    report.general_scores = [
        ScoreItem("general", names[i], names[i], s, "r") for i, s in enumerate(general)
    ]
    report.qa_scores = [
        ScoreItem("qa", f"Q{i + 1}·R1", f"Q{i + 1}", s, "r") for i, s in enumerate(qa)
    ]
    results = []
    for idx, cp in enumerate(q.checkpoints):
        status = "覆盖" if idx < covered else "未覆盖"
        if missing_core and cp.is_core:
            status = "未覆盖"
        results.append(
            CheckpointResult(cp.id, cp.description, status, "", cp.is_core)
        )
    report.checkpoints = results
    return report


# ---------------------------------------------------------------- 数学排版

def test_normalize_exponent():
    """^ 次方转 Unicode 上标：否则 Markdown 会把两个 ^ 之间的正文吞成上标。"""
    assert normalize_math("4.7536×10^5 与 -1×10^5") == "4.7536×10⁵ 与 -1×10⁵"
    assert normalize_math("3.2×10^-4") == "3.2×10⁻⁴"
    assert normalize_math("x^{n+1} 与 x^2y") == "xⁿ⁺¹ 与 x²y"
    assert normalize_math("10^6 的形式") == "10⁶ 的形式"


def test_normalize_exponent_edges():
    """LaTeX 片段不动；落单的 ^ 转义；已转好的不重复处理。"""
    assert normalize_math("$10^6$") == "$10^6$"
    assert normalize_math("10^ 后面没有内容") == "10\\^ 后面没有内容"
    assert normalize_math(r"已转义的 \^5") == r"已转义的 \^5"
    assert normalize_math("已经是 10⁵") == "已经是 10⁵"


def test_report_normalizes_exponents():
    """报告正文里不能残留裸 ^（除非已转义）。"""
    report = _make_report([4, 4, 4], [4, 4, 4], covered=8, missing_core=0)
    report.general_scores[0].rationale = "把 3.2×10^-4 与 6.5×10^6 讲清楚了"
    report.checkpoints[0].evidence = "3.18×10^4"
    markdown = render_report(report)
    assert "10⁻⁴" in markdown
    assert "10⁶" in markdown
    assert "10⁴" in markdown
    assert not re.search(r"(?<!\\)\^", markdown)


def test_report_escapes_pipe_in_table_cell():
    """理由里的绝对值 |A| 必须转义，否则表格会被撑成多列。"""
    report = _make_report([4, 4, 4], [4, 4, 4], covered=8, missing_core=0)
    question = GeneratedQuestion(
        round=1, persona_id="P1", persona_name="概念严谨型", text="为什么？"
    )
    report.qa_pairs = [QAPair(question=question, answer="因为……")]
    report.qa_scores[0].rationale = "没有区分 A 本身与 |A|，也未给出 1≤|A|<10"
    markdown = render_report(report)
    assert "\\|A\\|" in markdown
    row = next(line for line in markdown.splitlines() if "没有区分 A 本身" in line)
    assert row.count("|") - row.count("\\|") == 4  # 3 列 → 4 个列分隔符


def test_report_dedupes_suggestion_prefix():
    """模型偶尔把「【讲稿】」写两遍，报告里必须折叠成一个。"""
    report = _make_report([4, 4, 4], [4, 4, 4], covered=8, missing_core=0)
    report.suggestions = ["【讲稿】【讲稿】G2 规则要严谨", "【问答】R1 要演示过程"]
    markdown = render_report(report)
    assert "【讲稿】G2 规则要严谨" in markdown
    assert "【讲稿】【讲稿】" not in markdown
    assert "【问答】【问答】" not in markdown


# ---------------------------------------------------------------- 日志

def test_setup_logging_is_idempotent_and_writes_stderr(capsys):
    """重复调用只保留一个 handler；错误级别带 ✗ 前缀，且消息不落 stdout。"""
    import logging

    from edu_eval.logs import get_logger, setup_logging

    logger = setup_logging("DEBUG")
    setup_logging("DEBUG")
    handlers = [h for h in logger.handlers if getattr(h, "_edu_eval", False)]
    assert len(handlers) == 1
    assert handlers[0].stream is sys.stderr

    record = logging.LogRecord("edu_eval", logging.ERROR, __file__, 1, "坏掉了", None, None)
    assert handlers[0].format(record) == "✗ 坏掉了"

    get_logger("edu_eval.qa_gen").info("测试日志")
    captured = capsys.readouterr()
    assert "测试日志" in captured.err
    assert "测试日志" not in captured.out


def test_qa_gen_retry_goes_to_log():
    """提问生成重试是诊断信息，应记为 WARNING，而不是 print 到 stdout。"""
    import logging

    class _EmptyClient:
        """总返回空问题，逼迫重试耗尽。"""

        def chat_json(self, prompt: str, temperature: float = 0.5, task: str = "") -> dict:
            return {"questions": []}

    records: list[logging.LogRecord] = []

    class _Recorder(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("edu_eval")
    handler = _Recorder()
    logger.addHandler(handler)
    try:
        with pytest.raises(RuntimeError):
            generate_questions(load_question("M-CZ-001"), "讲稿" * 200, _EmptyClient())
    finally:
        logger.removeHandler(handler)

    assert any(r.levelno == logging.WARNING and "重试" in r.getMessage() for r in records)


# ---------------------------------------------------------------- 命令行

def test_cli_redirected_output_is_utf8(tmp_path: Path):
    """输出被重定向时（非 tty）应改走 UTF-8，不能因 GBK 编不了 ✓ 崩溃。"""
    import os
    import subprocess

    env = dict(os.environ, PYTHONIOENCODING="gbk")
    proc = subprocess.run(
        [
            sys.executable, "run.py", "run",
            "--lecture", "datasets/examples/M-CZ-001-高质量讲稿.md",
            "--answers", "datasets/examples/M-CZ-001-答案示例.json",
            "--dry-run", "--out", str(tmp_path / "out"),
        ],
        cwd=ROOT, capture_output=True, env=env, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    text = proc.stdout.decode("utf-8")
    assert "评估完成" in text
    assert "评级：" in text