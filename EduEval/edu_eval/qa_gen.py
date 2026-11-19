"""
虚拟学生提问生成：抽 3 类人设 → LLM 生成 3 问 → 校验去重。

校验做两件事:
  1. 结构校验：3 问齐备、人设不重复；
  2. 去重校验：两两之间「考察点」不得高度重叠（用规则+关键词粗筛，避免再调一次 LLM）。
     若去重不过，直接重新生成（最多 retry 次），仍不过则接受并打警告。
"""
import random

from .assets import fill, load_personas, load_prompt
from .config import config
from .llm import LLMClient
from .logs import get_logger
from .models import GeneratedQuestion, Persona, Question

logger = get_logger(__name__)

# 去重时的关键词组：命中同一组即视为考察点重叠
_TOPIC_GROUPS = [
    ["范围", "取值", "1≤A", "1 < A", "比 1 大", "比1大", "上限", "下限", "边界"],
    ["位数", "几个 0", "几个0", "次方", "指数", "数错"],
    ["负数", "小于 1", "小于1", "0.000", "负指数"],
    ["简洁", "更清楚", "为什么用", "必要性", "好处"],
]


def _overlap(a: str, b: str) -> bool:
    """判断两个问题是否落在同一考察点组。"""
    for group in _TOPIC_GROUPS:
        hit_a = any(kw in a for kw in group)
        hit_b = any(kw in b for kw in group)
        if hit_a and hit_b:
            return True
    return False


def check_distinct(questions: list[GeneratedQuestion]) -> tuple[bool, str]:
    """
    检查 3 问是否互不重复。

    Returns:
        (是否通过, 不通过原因)
    """
    if len(questions) < 2:
        return True, ""
    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            if _overlap(questions[i].text, questions[j].text):
                return False, f"第 {i + 1} 问与第 {j + 1} 问考察点重叠"
    return True, ""


def pick_personas(personas: list[Persona], count: int = 3, seed: int | None = None) -> list[Persona]:
    """从人设库随机抽 count 类（不重复）。seed 固定时结果可复现。"""
    rng = random.Random(seed)
    count = min(count, len(personas))
    return rng.sample(personas, count)


def generate_questions(
    question: Question,
    lecture: str,
    client: LLMClient,
    seed: int | None = None,
) -> list[GeneratedQuestion]:
    """
    为一篇讲稿生成 3 个学生提问。

    Args:
        question: 讲题
        lecture: 被试的逐字讲稿
        client: LLM 客户端（dry-run 时返回桩数据）
        seed: 随机种子，便于复现
    Returns:
        3 个 GeneratedQuestion（按轮次排序）
    """
    personas = pick_personas(
        load_personas(),
        count=config["qa"]["persona_count"],
        seed=seed,
    )
    rounds = config["qa"]["rounds"]
    max_retry = 2
    last: list[GeneratedQuestion] = []

    for attempt in range(max_retry + 1):
        prompt = _build_prompt(question, lecture, personas)
        data = client.chat_json(
            prompt,
            temperature=config["temperature"]["qa"] + attempt * 0.1,
            task="qa_generation",
        )
        questions = _parse_questions(data, personas)

        ok, reason = check_distinct(questions) if questions else (False, "问题数量不足")
        if ok and len(questions) == rounds:
            return questions
        last = questions
        logger.warning("问题校验未通过（%s），重试 %d/%d", reason, attempt + 1, max_retry)

    if last:
        logger.warning("已达重试上限，采用最后一次生成结果（请在报告中留意问题质量）")
        return last
    raise RuntimeError("问题生成失败：未返回有效问题")


def _build_prompt(question: Question, lecture: str, personas: list[Persona]) -> str:
    """拼装提问生成提示词。"""
    persona_block = "\n".join(
        f"- {p.id}｜{p.name}：{p.features}；提问视角：{p.perspective}"
        for p in personas
    )
    pitfalls = "\n".join(f"- {p.description}" for p in question.pitfalls) or "（无）"
    template = load_prompt("qa_generation")
    return fill(
        template,
        title=question.title,
        grade=question.grade,
        task=question.task,
        lecture=_truncate(lecture, config["limits"]["max_script_words"]),
        personas=persona_block,
        pitfalls=pitfalls,
        rounds=config["qa"]["rounds"],
    )


def _parse_questions(data: dict, personas: list[Persona]) -> list[GeneratedQuestion]:
    """把模型输出的 JSON 解析成 GeneratedQuestion 列表。"""
    persona_map = {p.id: p for p in personas}
    result = []
    for item in data.get("questions", []):
        persona_id = item.get("persona_id", "")
        persona = persona_map.get(persona_id)
        name = item.get("persona_name") or (persona.name if persona else "未知类型")
        result.append(
            GeneratedQuestion(
                round=int(item.get("round", len(result) + 1)),
                persona_id=persona_id,
                persona_name=name,
                text=str(item.get("text", "")).strip(),
                reference_points=list(item.get("reference_points", [])),
            )
        )
    result.sort(key=lambda q: q.round)
    return result


def _truncate(text: str, limit: int) -> str:
    """超长讲稿截断（按字符数，够用）。"""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n……（讲稿过长，已截断）"