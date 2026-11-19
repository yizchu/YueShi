"""
静态资产加载：题库、人设、提示词。

目录约定（相对项目根）:
    datasets/questions/*.json     每题一个文件
    datasets/personas/personas.json
    edu_eval/prompts/*.md
"""
import json
import random
from pathlib import Path

from .config import path_config
from .models import Question, Checkpoint, Pitfall, Persona

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def _question_dir() -> Path:
    return path_config()["datasets"] / "questions"


def _persona_file() -> Path:
    return path_config()["datasets"] / "personas" / "personas.json"


def list_questions() -> list[Question]:
    """列出题库里所有题目（按文件名字典序）。"""
    result = []
    for f in sorted(_question_dir().glob("*.json")):
        result.append(_parse_question(f))
    return result


def draw_question(seed: int | None = None) -> Question:
    """
    随机抽一道题（抽题环节，不给学生人设）。

    seed 只用于测试与实验复现：同一个 seed 抽到同一题；不传则真正随机。
    题库为空时抛 FileNotFoundError。
    """
    questions = list_questions()
    if not questions:
        raise FileNotFoundError("题库为空，无法抽题")
    picker = random.Random(seed) if seed is not None else random.SystemRandom()
    return picker.choice(questions)


def load_question(question_id: str) -> Question:
    """
    按 ID 取题目。支持传完整 ID（M-CZ-001）或前缀（M-CZ-001 的前缀）。

    找不到时抛 FileNotFoundError，并列出可用 ID 帮助排查。
    """
    files = sorted(_question_dir().glob("*.json"))
    for f in files:
        if f.stem == question_id or f.stem.startswith(question_id):
            return _parse_question(f)
    available = ", ".join(f.stem for f in files) or "（题库为空）"
    raise FileNotFoundError(f"未找到题目 {question_id}；可用：{available}")


def _parse_question(path: Path) -> Question:
    """把 JSON 解析成 Question；缺字段时给安全默认值。"""
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    checkpoints = [
        Checkpoint(
            id=cp["id"],
            description=cp["description"],
            is_core=bool(cp.get("is_core", False)),
            category=cp.get("category", "知识点覆盖"),
        )
        for cp in raw.get("checkpoints", [])
    ]
    pitfalls = [
        Pitfall(id=p["id"], description=p["description"])
        for p in raw.get("pitfalls", [])
    ]
    return Question(
        id=raw.get("id", path.stem),
        title=raw.get("title", path.stem),
        grade=raw.get("grade", ""),
        task=raw.get("task", ""),
        checkpoints=checkpoints,
        pitfalls=pitfalls,
        reference_points=raw.get("reference_points", ""),
    )


def load_personas() -> list[Persona]:
    """读取 5 类虚拟学生人设。"""
    raw = json.loads(_persona_file().read_text(encoding="utf-8-sig"))
    return [
        Persona(
            id=p["id"],
            name=p["name"],
            features=p["features"],
            perspective=p["perspective"],
        )
        for p in raw
    ]


def load_prompt(name: str) -> str:
    """读取提示词模板（Markdown，含 {占位符}）。"""
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"未找到提示词：{path}")
    return path.read_text(encoding="utf-8-sig")


def fill(template: str, **kwargs) -> str:
    """
    填充提示词占位符。

    用朴素替换而非 str.format：提示词里含 JSON 示例（花括号），
    format 会把 {"questions" 当成字段名而报错。
    """
    text = template
    for key, value in kwargs.items():
        text = text.replace("{" + key + "}", str(value))
    return text