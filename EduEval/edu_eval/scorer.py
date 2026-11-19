"""
评分：通用标准 3 项 + 特殊标准（采分点逐条）+ 问答标准 3 维 × 3 轮 + 评级。

评级规则（MVP 版，门槛优先）:
    核心采分点未覆盖        → 最高「待改进」
    未覆盖采分点 ≥ 半数      → 最高「待改进」
    通用/问答均分 < 3        → 最高「待改进」
    通用/问答均分 ≥ 4.5      → 「优秀」
    通用/问答均分 ≥ 3.8      → 「良好」
    通用/问答均分 ≥ 3.0      → 「合格」
    其余                    → 「待改进」

注意：权重与阈值均为初值，待专家评分校准后调整（见 docs/requirements 待决问题）。
"""
from .assets import fill, load_prompt
from .config import config
from .llm import LLMClient
from .models import (
    QAPair, Question, ScoreItem, CheckpointResult, Report,
)

RATINGS = ["优秀", "良好", "合格", "待改进"]


def score_all(
    question: Question,
    lecture: str,
    qa_pairs: list[QAPair],
    client: LLMClient,
) -> tuple[list[ScoreItem], list[ScoreItem], list[CheckpointResult], list[str]]:
    """
    执行全部评分。

    Returns:
        (通用标准得分, 问答标准得分, 采分点结果, 改进建议)
    """
    general = _score_general(question, lecture, client)
    checkpoints = _score_checkpoints(question, lecture, client)
    qa_scores = _score_qa(question, qa_pairs, client)
    suggestions = _build_suggestions(question, general, checkpoints, qa_scores, client)
    return general, qa_scores, checkpoints, suggestions


# ---------------------------------------------------------------- 通用标准

def _score_general(question: Question, lecture: str, client: LLMClient) -> list[ScoreItem]:
    """讲稿的通用标准评分（G1/G2/G3）。"""
    prompt = fill(
        load_prompt("score_general"),
        title=question.title,
        grade=question.grade,
        task=question.task,
        reference_points=question.reference_points,
        lecture=_truncate(lecture),
    )
    data = client.chat_json(
        prompt,
        temperature=config["temperature"]["score"],
        task="score_general",
    )
    items = []
    for dim in data.get("dimensions", []):
        items.append(
            ScoreItem(
                category="general",
                dimension=dim.get("dimension", ""),
                name=dim.get("name", ""),
                score=_clamp(dim.get("score", 3)),
                rationale=dim.get("rationale", ""),
                evidence=dim.get("evidence", ""),
            )
        )
    return items


# ---------------------------------------------------------------- 采分点

def _score_checkpoints(
    question: Question,
    lecture: str,
    client: LLMClient,
) -> list[CheckpointResult]:
    """逐条判定采分点是否覆盖。"""
    cp_block = "\n".join(
        f"- {cp.id}（{'核心' if cp.is_core else '普通'}）：{cp.description}"
        for cp in question.checkpoints
    )
    prompt = fill(
        load_prompt("score_checkpoint"),
        title=question.title,
        lecture=_truncate(lecture),
        checkpoints=cp_block,
    )
    data = client.chat_json(
        prompt,
        temperature=config["temperature"]["score"],
        task="score_checkpoint",
    )
    judged = {item.get("checkpoint_id"): item for item in data.get("checkpoints", [])}
    results = []
    for cp in question.checkpoints:
        item = judged.get(cp.id, {})
        results.append(
            CheckpointResult(
                checkpoint_id=cp.id,
                description=cp.description,
                status=item.get("status", "未覆盖"),
                evidence=item.get("evidence", ""),
                is_core=cp.is_core,
            )
        )
    return results


# ---------------------------------------------------------------- 问答标准

def _score_qa(question: Question, qa_pairs: list[QAPair], client: LLMClient) -> list[ScoreItem]:
    """3 轮问答的评分（每轮 Q1/Q2/Q3）。"""
    qa_block = _format_qa(qa_pairs)
    prompt = fill(
        load_prompt("score_qa"),
        title=question.title,
        qa_block=qa_block,
    )
    data = client.chat_json(
        prompt,
        temperature=config["temperature"]["score"],
        task="score_qa",
    )
    items = []
    for round_item in data.get("rounds", []):
        rnd = round_item.get("round", "")
        for dim in round_item.get("scores", []):
            items.append(
                ScoreItem(
                    category="qa",
                    dimension=f"{dim.get('dimension', '')}·R{rnd}",
                    name=dim.get("name", ""),
                    score=_clamp(dim.get("score", 3)),
                    rationale=dim.get("rationale", ""),
                    evidence=dim.get("evidence", ""),
                )
            )
    return items


def _format_qa(qa_pairs: list[QAPair]) -> str:
    """把 3 轮问答拼成提示词里的文本块。"""
    blocks = []
    for pair in qa_pairs:
        q = pair.question
        refs = "\n".join(f"    · {r}" for r in q.reference_points) or "    · （无）"
        blocks.append(
            f"【第 {q.round} 轮 · {q.persona_name}】\n"
            f"学生提问：{q.text}\n"
            f"参考应答要点：\n{refs}\n"
            f"被试回答：{pair.answer}"
        )
    return "\n\n".join(blocks)


# ---------------------------------------------------------------- 改进建议

def _build_suggestions(
    question: Question,
    general: list[ScoreItem],
    checkpoints: list[CheckpointResult],
    qa_scores: list[ScoreItem],
    client: LLMClient,
) -> list[str]:
    """
    生成改进建议。仅当存在不足时才调用 LLM；全部优秀则返回空列表。
    """
    weak_general = [s for s in general if s.score < 4]
    weak_qa = [s for s in qa_scores if s.score < 4]
    missing = [cp for cp in checkpoints if not cp.covered]
    if not (weak_general or weak_qa or missing):
        return []

    prompt = fill(
        load_prompt("suggestions"),
        title=question.title,
        general=_format_scores(general),
        checkpoints=_format_checkpoints(checkpoints),
        qa_scores=_format_scores(qa_scores),
    )
    data = client.chat_json(
        prompt,
        temperature=config["temperature"]["suggestion"],
        task="suggestions",
    )
    return [
        f"【{item.get('target', '')}】{item.get('text', '')}"
        for item in data.get("suggestions", [])
        if item.get("text")
    ]


def _format_scores(items: list[ScoreItem]) -> str:
    lines = [
        f"- {s.name}（{s.dimension}）：{s.score}/5　{s.rationale}"
        for s in items
    ]
    return "\n".join(lines) or "（无）"


def _format_checkpoints(items: list[CheckpointResult]) -> str:
    lines = [
        f"- {cp.checkpoint_id}（{'核心' if cp.is_core else '普通'}）"
        f"{cp.description}：{cp.status}　{cp.evidence}"
        for cp in items
    ]
    return "\n".join(lines) or "（无）"


# ---------------------------------------------------------------- 评级

def make_rating(report: Report) -> str:
    """
    按门槛规则给出评级。

    规则见模块 docstring；核心采分点缺失一票限制上限。
    """
    general_avg = _avg([s.score for s in report.general_scores])
    qa_avg = _avg([s.score for s in report.qa_scores])
    report.general_avg = general_avg
    report.qa_avg = qa_avg

    overall = _avg([v for v in (general_avg, qa_avg) if v > 0]) if (general_avg or qa_avg) else 0

    if report.missing_core:
        return "待改进"
    if report.total_checkpoints and report.covered_count < report.total_checkpoints / 2:
        return "待改进"
    if overall >= 4.5:
        return "优秀"
    if overall >= 3.8:
        return "良好"
    if overall >= 3.0:
        return "合格"
    return "待改进"


# ---------------------------------------------------------------- 工具

def _avg(values: list[float]) -> float:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0


def _clamp(value, low: int = 1, high: int = 5) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return float(low)
    return max(low, min(high, num))


def _truncate(text: str) -> str:
    limit = config["limits"]["max_script_words"]
    if len(text) <= limit:
        return text
    return text[:limit] + "\n……（讲稿过长，已截断）"