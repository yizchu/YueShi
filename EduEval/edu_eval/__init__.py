"""
EduEval
初中数学讲题教学能力评估智能体。

给定一道讲题，被试提交逐字讲稿，系统以 3 类虚拟学生各提 1 问，
被试依次作答，最后由 LLM 按「通用标准 + 特殊标准（采分点）+ 问答标准」评分，
输出评级与改进建议。

用法:
    python -m edu_eval run --lecture 讲稿.md                        # 随机抽题
    python -m edu_eval run --question M-CZ-001 --lecture 讲稿.md     # 指定题目（实验复现）
    python -m edu_eval list
"""

__version__ = "0.1.0"

from .config import config
from .models import (
    Question, Checkpoint, Persona, GeneratedQuestion,
    QAPair, ScoreItem, CheckpointResult, Report,
)
from .assets import draw_question, load_question, load_personas, list_questions
from .logs import get_logger, setup_logging
from .qa_gen import generate_questions
from .scorer import score_all
from .reporter import render_report

__all__ = [
    "config",
    "Question", "Checkpoint", "Persona", "GeneratedQuestion",
    "QAPair", "ScoreItem", "CheckpointResult", "Report",
    "load_question", "load_personas", "list_questions", "draw_question",
    "generate_questions", "score_all", "render_report",
    "setup_logging", "get_logger",
]