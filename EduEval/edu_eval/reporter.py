"""
报告生成：把评分结果拼装成 Markdown。

不依赖模板引擎，直接用 f-string 与 "\n".join 拼接，结构固定反而更好维护。
"""
import re
from datetime import datetime

from .mathfmt import normalize_math
from .models import Report

STATUS_ICON = {"覆盖": "✅", "部分覆盖": "⚠️", "未覆盖": "❌"}

# 模型偶尔会把「【讲稿】」这类分区前缀写两遍，渲染前折叠一次
_DUP_PREFIX = re.compile(r"(【[^】]{1,8}】)\1+")


def render_report(report: Report) -> str:
    """
    渲染完整报告 Markdown。

    最后统一做一次数学排版归一化：把 LLM 或讲稿里的 ^ 次方改成 Unicode
    上标，否则 Markdown 渲染器会把两个 ^ 之间的正文吞成上标。
    """
    sections = [
        _header(report),
        _rating(report),
        _overview(report),
        _general_section(report),
        _checkpoint_section(report),
        _qa_section(report),
        _suggestions_section(report),
        _appendix(report),
    ]
    return normalize_math("\n\n".join(s for s in sections if s) + "\n")


# ---------------------------------------------------------------- 各段落

def _header(report: Report) -> str:
    q = report.question
    return "\n".join([
        "# 教学能力评估报告",
        "",
        "| | |",
        "|---|---|",
        f"| 评估编号 | {report.session_id} |",
        f"| 题目 | 《{_cell(q.title)}》（{_cell(q.grade)}） |",
        f"| 讲稿字数 | {len(report.lecture)} 字 |",
        f"| 评估时间 | {report.meta.get('time', _now())} |",
    ])


def _rating(report: Report) -> str:
    core_note = "**核心采分点已覆盖**"
    if report.missing_core:
        ids = "、".join(cp.checkpoint_id for cp in report.missing_core)
        core_note = f"**核心采分点缺失（{ids}），评级受限**"

    lines = [
        f"## 评级：**{report.rating}**",
        "",
        f"> 讲稿均分 {report.general_avg:.1f} / 5　｜　"
        f"问答均分 {report.qa_avg:.1f} / 5　｜　"
        f"采分点 {report.covered_count} / {report.total_checkpoints} 覆盖",
        f"> {core_note}",
    ]
    if report.missing_core or report.covered_count < report.total_checkpoints / 2:
        lines.append(">")
        lines.append("> ⚠️ 已触发门槛规则：核心知识点缺失或覆盖不足，评级最高「待改进」。")
    return "\n".join(lines)


def _overview(report: Report) -> str:
    rows = ["| 部分 | 项目 | 得分 |", "|---|---|---|"]
    for item in report.general_scores:
        rows.append(f"| 讲稿 | {item.name}（{item.dimension}） | {item.score:.0f} / 5 |")
    rows.append(
        f"| 讲稿 | 特殊标准（采分点） | {report.covered_count} / "
        f"{report.total_checkpoints} 覆盖 |"
    )
    for item in report.qa_scores:
        rows.append(f"| 问答 | {item.name}（{item.dimension}） | {item.score:.0f} / 5 |")
    return "## 得分总览\n\n" + "\n".join(rows)


def _general_section(report: Report) -> str:
    lines = ["## 一、讲稿评估（通用标准）"]
    if not report.general_scores:
        lines.append("")
        lines.append("（无评分数据）")
        return "\n".join(lines)

    for item in report.general_scores:
        lines.append("")
        lines.append(f"### {item.dimension} {item.name} —— {item.score:.0f} / 5")
        lines.append("")
        lines.append(f"**理由**：{item.rationale}")
        if item.evidence:
            lines.append("")
            lines.append("**证据**：")
            lines.append(f"> {item.evidence}")
    return "\n".join(lines)


def _checkpoint_section(report: Report) -> str:
    lines = ["### 特殊标准 · 采分点判定", ""]
    if not report.checkpoints:
        lines.append("（无采分点数据）")
        return "\n".join(lines)

    lines.append("| # | 采分点 | 判定 | 证据 |")
    lines.append("|---|---|---|---|")
    for cp in report.checkpoints:
        icon = STATUS_ICON.get(cp.status, "❓")
        desc = _cell(cp.description)
        if cp.is_core:
            desc = f"**{desc}（核心）**"
        evidence = _cell(cp.evidence) or "—"
        lines.append(f"| {cp.checkpoint_id} | {desc} | {icon} {cp.status} | {evidence} |")

    partial = [cp for cp in report.checkpoints if cp.status == "部分覆盖"]
    if partial:
        lines.append("")
        lines.append(
            "> ⚠️ 部分覆盖：" + "、".join(cp.checkpoint_id for cp in partial)
            + " —— 给出了结果但未讲清方法，学生换个数仍可能出错。"
        )
    return "\n".join(lines)


def _qa_section(report: Report) -> str:
    lines = ["## 二、问答评估"]
    if not report.qa_pairs:
        lines.append("")
        lines.append("（无问答数据）")
        return "\n".join(lines)

    for pair in report.qa_pairs:
        q = pair.question
        lines.append("")
        lines.append(f"### 第 {q.round} 轮 · {q.persona_name}")
        lines.append("")
        lines.append("**学生提问**")
        lines.append(f"> {q.text}")
        lines.append("")
        lines.append("**被试回答**")
        lines.append(f"> {_indent_quote(pair.answer)}")

        round_scores = [s for s in report.qa_scores if s.dimension.endswith(f"R{q.round}")]
        if round_scores:
            lines.append("")
            lines.append("**评分**")
            lines.append("")
            lines.append("| 项目 | 得分 | 说明 |")
            lines.append("|---|---|---|")
            for item in round_scores:
                lines.append(
                    f"| {_cell(item.name)} | {item.score:.0f} / 5 | {_cell(item.rationale)} |"
                )
    return "\n".join(lines)


def _suggestions_section(report: Report) -> str:
    lines = ["## 三、改进建议"]
    if not report.suggestions:
        lines.append("")
        lines.append("各项表现均达标，暂无改进建议。")
        return "\n".join(lines)

    for idx, text in enumerate(report.suggestions, 1):
        lines.append("")
        lines.append(f"{idx}. {_dedupe_prefix(text)}")
    return "\n".join(lines)


def _dedupe_prefix(text: str) -> str:
    """把重复的分区前缀（如「【讲稿】【讲稿】」）折叠成一个。"""
    return _DUP_PREFIX.sub(r"\1", text)


def _appendix(report: Report) -> str:
    meta = report.meta
    return "\n".join([
        "---",
        "",
        "## 附录 · 评估元信息",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 模型 | {meta.get('model', '—')} |",
        f"| 采样次数 | {meta.get('samples', 1)} |",
        f"| LLM 调用次数 | {meta.get('calls', 0)} |",
        f"| Token 消耗 | {meta.get('tokens', 0)} |",
        f"| 运行模式 | {'dry-run（桩数据）' if meta.get('dry_run') else '真实调用'} |",
        f"| 生成时间 | {_now()} |",
    ])


# ---------------------------------------------------------------- 工具

def _indent_quote(text: str) -> str:
    """多行引用：每行前补 >，避免 Markdown 引用断裂。"""
    return "\n> ".join(line for line in text.strip().splitlines() if line is not None)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _cell(text: str) -> str:
    """
    Markdown 表格单元格转义：竖线会被当成列分隔符，换行会截断整行。

    评分理由里出现 |A|（绝对值）、1≤|A|<10 这类写法时，不转义会把
    「说明」列撑成多列，表格错位。
    """
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ")