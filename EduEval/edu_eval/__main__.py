"""
python -m edu_eval —— 教学能力评估命令行入口

用法:
    python -m edu_eval list
    python -m edu_eval run --lecture 讲稿.md                      # 随机抽题
    python -m edu_eval run --question M-CZ-001 --lecture 讲稿.md  # 指定题目
    python -m edu_eval run --lecture 讲稿.md --dry-run
    python -m edu_eval run --lecture 讲稿.md --answers 答案.json
    python -m edu_eval run --session workspace/EV-20261105-0001

约定:
  * 题目默认随机抽（抽题环节不给学生人设）；--question 仅用于复现实验；
  * 讲稿走文件（1000+ 字在编辑器里写更现实）；
  * 问答走终端（问题打印出来后当场输入，多行、空行结束）；
  * --dry-run 用桩数据跑通全链路，不需要 API 密钥；
  * stdout 只放交互与结果，运行状态和错误走 stderr 日志。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .assets import draw_question, load_question, list_questions
from .config import config, path_config, ROOT_DIR
from .llm import LLMClient, LLMError
from .logs import get_logger, setup_logging
from .models import (
    CheckpointResult, GeneratedQuestion, QAPair, Question, Report, ScoreItem,
)
from .qa_gen import generate_questions
from .reporter import render_report
from .session_store import reserve_session, write_snapshot
from .scorer import score_all, make_rating

logger = get_logger(__name__)


def _ensure_utf8_stdout() -> None:
    """
    输出被重定向（管道/文件）时强制 UTF-8。

    Windows 下重定向会把编码退化为 GBK，而提示语里有 ✓ · → 等符号，
    直接打印会抛 UnicodeEncodeError；控制台（isatty）保持原样，不乱码。
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main() -> int:
    """解析命令行并分发到 list / run。"""
    _ensure_utf8_stdout()
    setup_logging()
    parser = argparse.ArgumentParser(
        prog="edu_eval",
        description="初中数学讲题教学能力评估（讲稿 + 3 轮虚拟学生问答 → 评级报告）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- list ----
    p_list = sub.add_parser("list", help="列出题库")
    p_list.add_argument("--json", action="store_true", help="以 JSON 输出（bool）")

    # ---- run ----
    p_run = sub.add_parser("run", help="执行一次评估")
    p_run.add_argument("--question", "-q", type=str, default="",
                       help="题目 ID，如 M-CZ-001；省略则随机抽题（str）")
    p_run.add_argument("--lecture", "-l", type=str, default="",
                       help="讲稿文件路径（str）")
    p_run.add_argument("--answers", "-a", type=str, default="",
                       help="答案 JSON 文件路径，非交互模式（str）")
    p_run.add_argument("--session", "-s", type=str, default="",
                       help="续跑已有会话目录（str）")
    p_run.add_argument("--out", "-o", type=str, default="",
                       help="输出目录，默认 workspace/<会话编号>（str）")
    p_run.add_argument("--dry-run", action="store_true",
                       help="用桩数据，不调用 LLM（bool）")
    p_run.add_argument("--seed", type=int, default=None,
                       help="人设抽取随机种子，便于复现（int）")
    p_run.add_argument("--candidate", type=str, default="candidate-001",
                       help="被试标识（str）")

    args: argparse.Namespace = parser.parse_args()
    if args.command == "list":
        return cmd_list(args)
    return cmd_run(args)


# ---------------------------------------------------------------- list

def cmd_list(args: argparse.Namespace) -> int:
    """打印题库清单。"""
    questions: list[Question] = list_questions()
    if not questions:
        logger.error("题库为空，请先在 datasets/questions/ 下放题目 JSON")
        return 1
    if args.json:
        print(json.dumps(
            [{"id": q.id, "title": q.title, "grade": q.grade,
              "checkpoints": len(q.checkpoints)} for q in questions],
            ensure_ascii=False, indent=2,
        ))
        return 0
    print(f"题库共 {len(questions)} 题：\n")
    for q in questions:
        core = len(q.core_checkpoints)
        print(f"  {q.id}  {q.title}（{q.grade}）"
              f"  采分点 {len(q.checkpoints)} 条（核心 {core}）")
    return 0


# ---------------------------------------------------------------- run

def cmd_run(args: argparse.Namespace) -> int:
    """执行完整评估流程。"""
    print("=" * 60)
    print("  EduEval · 教学能力评估（初中数学）")
    print("=" * 60)

    # 1. 确定会话与题目
    stored_questions: list[GeneratedQuestion] = []
    stored_answers: dict[str, str] = {}
    if args.session:
        session_dir = Path(args.session)
        if not session_dir.is_absolute():
            session_dir = ROOT_DIR / session_dir
        question, lecture, stored_questions, stored_answers = _resume(
            session_dir, args.question, args.lecture
        )
        session_id: str = session_dir.name
    else:
        if args.question:
            try:
                question = load_question(args.question)
            except FileNotFoundError as exc:
                logger.error("%s", exc)
                return 1
        else:
            try:
                question = draw_question(args.seed)
            except FileNotFoundError as exc:
                logger.error("%s", exc)
                return 1
            logger.info("已随机抽题（抽题环节不提供学生人设）")
        lecture = _read_lecture(args.lecture)
        if lecture is None:
            return 1
        if args.out:
            session_id = make_session_id()
            session_dir = Path(args.out)
        else:
            session_dir = reserve_session(path_config()["workspace"])
            session_id = session_dir.name
    session_dir.mkdir(parents=True, exist_ok=True)

    print(f"✓ 题目：{question.label}")
    print(f"✓ 讲稿：{len(lecture)} 字")

    # 2. 构建 LLM 客户端
    try:
        client = LLMClient(dry_run=args.dry_run)
    except LLMError as exc:
        logger.error("%s", exc)
        return 1
    if args.dry_run:
        logger.info("dry-run 模式：使用桩数据，不调用真实模型")

    # 3. 提问：续跑时复用已有问题，避免每次重生成导致问题变化
    questions: list[GeneratedQuestion]
    if stored_questions:
        questions = stored_questions
        logger.info("复用已生成的 %d 个提问", len(questions))
    else:
        logger.info("正在抽取学生人设、生成提问…")
        try:
            questions = generate_questions(question, lecture, client, seed=args.seed)
        except (LLMError, RuntimeError) as exc:
            logger.error("提问生成失败：%s", exc)
            return 1
    for q in questions:
        done = "（已回答）" if stored_answers.get(str(q.round)) else ""
        logger.info("第 %d 轮　%s%s", q.round, q.persona_name, done)

    # 4. 三轮问答：已答的跳过，只问缺的
    # 答案来源：命令行 --answers 打底，会话里已答的优先（避免覆盖已有进度）
    answers: dict[str, str] = {**_load_answers(args.answers), **stored_answers}
    qa_pairs: list[QAPair] = []
    for q in questions:
        existing = answers.get(str(q.round), "")
        if existing:
            qa_pairs.append(QAPair(question=q, answer=existing))
            print(f"\n──── 第 {q.round} 轮 · {q.persona_name} ────")
            print(f"  {q.text}")
            logger.info("已载入既有回答（%d 字）", len(existing))
            continue

        print(f"\n──── 第 {q.round} 轮 · {q.persona_name} ────")
        print(f"  {q.text}")
        answer: str | None = ask_answer(q)
        if answer is None:
            _save_progress(session_dir, session_id, question, lecture, qa_pairs, questions, args)
            logger.info("进度已保存，下次可用 --session 续跑")
            return 0
        qa_pairs.append(QAPair(question=q, answer=answer))
        # 每答一轮立即落盘，保证中断不丢
        _save_progress(session_dir, session_id, question, lecture, qa_pairs, questions, args)

    # 5. 评分
    logger.info("正在评分…")
    try:
        general: list[ScoreItem]
        qa_scores: list[ScoreItem]
        checkpoints: list[CheckpointResult]
        suggestions: list[str]
        general, qa_scores, checkpoints, suggestions = score_all(
            question, lecture, qa_pairs, client
        )
    except LLMError as exc:
        logger.error("评分失败：%s", exc)
        return 1

    # 6. 组装与渲染
    report: Report = Report(
        session_id=session_id,
        question=question,
        lecture=lecture,
        qa_pairs=qa_pairs,
        general_scores=general,
        qa_scores=qa_scores,
        checkpoints=checkpoints,
        suggestions=suggestions,
        meta={
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "model": "dry-run" if args.dry_run else config["llm"]["model"],
            "samples": 1,
            "dry_run": args.dry_run,
            **client.stats(),
        },
    )
    report.rating = make_rating(report)

    markdown: str = render_report(report)
    report_path: Path = session_dir / "report.md"
    write_snapshot(report_path, markdown)
    write_snapshot(
        session_dir / "session.json", json.dumps(_session_payload(report, args), ensure_ascii=False, indent=2),
    )

    print_summary(report, report_path)
    return 0


# ---------------------------------------------------------------- 交互

def ask_answer(question: GeneratedQuestion) -> str | None:
    """
    打印一问并读取多行回答。空行结束；输入 q 退出；r 重写。

    Returns:
        回答文本；用户输入 q 时返回 None
    """
    print("\n" + "─" * 60)
    print(f" 第 {question.round} 问 / 共 3 问　｜　学生类型：{question.persona_name}")
    print("─" * 60)
    print(f"\n  {question.text}\n")
    print("─" * 60)

    min_words = config["limits"]["min_answer_words"]
    while True:
        print("请输入你的回答（多行，空行结束；输入 q 退出）：")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                return None
            if line.strip() == "":
                break
            if not lines and line.strip() == "q":
                return None
            lines.append(line)
        answer = "\n".join(lines).strip()
        if len(answer) >= min_words:
            logger.info("已接收 %d 字", len(answer))
            confirm = input("  Enter 确认提交　｜　r 重新作答：").strip().lower()
            if confirm != "r":
                return answer
        else:
            logger.warning("回答仅 %d 字，低于下限 %d 字，请补充。", len(answer), min_words)


# ---------------------------------------------------------------- 辅助

def make_session_id() -> str:
    return "EV-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def _read_lecture(path: str) -> str | None:
    """读讲稿并校验字数。"""
    if not path:
        logger.error("请用 --lecture 指定讲稿文件")
        return None
    file = Path(path)
    if not file.is_absolute():
        candidate = ROOT_DIR / path
        file = candidate if candidate.exists() else file
    if not file.exists():
        logger.error("未找到讲稿文件：%s", path)
        return None
    text = file.read_text(encoding="utf-8-sig").strip()
    min_words = config["limits"]["min_script_words"]
    if len(text) < min_words:
        logger.error("讲稿仅 %d 字，低于下限 %d 字", len(text), min_words)
        return None
    return text


def _resume(
    session_dir: Path,
    question_id: str,
    lecture_path: str,
) -> tuple[Question, str, list[GeneratedQuestion], dict[str, str]]:
    """
    续跑：从已有会话目录恢复题目、讲稿、已生成的问题与已回答内容。

    Returns:
        (question, lecture, stored_questions, stored_answers)
    """
    meta_file = session_dir / "session.json"
    question = load_question(question_id) if question_id else None
    lecture = None
    if lecture_path:
        lecture = _read_lecture(lecture_path)
    stored_questions: list[GeneratedQuestion] = []
    stored_answers: dict[str, str] = {}

    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8-sig"))
        if question is None and meta.get("questionId"):
            question = load_question(meta["questionId"])
        if lecture is None:
            lecture = meta.get("lecture", "")
        stored_questions = _parse_stored_questions(meta.get("qa", []))
        stored_answers = {
            str(item["round"]): item.get("answer", "")
            for item in meta.get("qa", [])
            if item.get("answer")
        }

    if question is None:
        raise SystemExit("续跑需要 --question（或会话中存在 questionId）")
    if not lecture:
        raise SystemExit("续跑需要 --lecture（或会话中已有讲稿）")
    logger.info("续跑会话：%s", session_dir.name)
    return question, lecture, stored_questions, stored_answers


def _parse_stored_questions(qa_items: list[dict]) -> list[GeneratedQuestion]:
    """把存档里的 qa 转回 GeneratedQuestion 列表。"""
    from .models import GeneratedQuestion

    result = []
    for item in qa_items:
        result.append(
            GeneratedQuestion(
                round=int(item["round"]),
                persona_id=item.get("personaId", ""),
                persona_name=item.get("personaName", ""),
                text=item.get("questionText", ""),
                reference_points=list(item.get("referencePoints", [])),
            )
        )
    result.sort(key=lambda q: q.round)
    return result


def _save_progress(
    session_dir: Path,
    session_id: str,
    question: Question,
    lecture: str,
    qa_pairs: list[QAPair],
    questions: list[GeneratedQuestion],
    args: argparse.Namespace,
) -> None:
    """
    中途落盘：每答一轮就写一次 session.json，保证 Ctrl+C / 断网不丢进度。

    未回答的轮次也会写入（answer 为空），下次可由此恢复提问本身。
    """
    answered = {pair.question.round: pair.answer for pair in qa_pairs}
    payload = {
        "sessionId": session_id,
        "questionId": question.id,
        "candidateId": getattr(args, "candidate", ""),
        "lecture": lecture,
        "status": "in_progress",
        "qa": [
            {
                "round": q.round,
                "personaId": q.persona_id,
                "personaName": q.persona_name,
                "questionText": q.text,
                "referencePoints": q.reference_points,
                "answer": answered.get(q.round, ""),
            }
            for q in questions
        ],
        "meta": {"dry_run": getattr(args, "dry_run", False)},
    }
    write_snapshot(
        session_dir / "session.json", json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _load_answers(path: str) -> dict[str, str]:
    """非交互模式：从 JSON 读答案，形如 {"1": "...", "2": "...", "3": "..."}。"""
    if not path:
        return {}
    file = Path(path)
    if not file.is_absolute():
        candidate = ROOT_DIR / path
        file = candidate if candidate.exists() else file
    if not file.exists():
        logger.warning("答案文件不存在：%s，转为交互模式", path)
        return {}
    return json.loads(file.read_text(encoding="utf-8-sig"))


def _session_payload(report: Report, args: argparse.Namespace) -> dict:
    """会话存档（便于复现与后续重评）。"""
    return {
        "sessionId": report.session_id,
        "questionId": report.question.id,
        "candidateId": args.candidate,
        "lecture": report.lecture,
        "qa": [
            {
                "round": pair.question.round,
                "personaId": pair.question.persona_id,
                "personaName": pair.question.persona_name,
                "questionText": pair.question.text,
                "referencePoints": pair.question.reference_points,
                "answer": pair.answer,
            }
            for pair in report.qa_pairs
        ],
        "rating": report.rating,
        "meta": report.meta,
    }


def print_summary(report: Report, report_path: Path) -> None:
    """终端摘要（不用制表框，避免中文双宽导致错位）。"""
    print("\n" + "=" * 60)
    print("  ✓ 评估完成")
    print("-" * 60)
    print(f"  评级：{report.rating}")
    print(f"  讲稿均分 {report.general_avg:.1f}　｜　问答均分 {report.qa_avg:.1f}"
          f"　｜　采分点 {report.covered_count}/{report.total_checkpoints}")
    if report.missing_core:
        ids = "、".join(cp.checkpoint_id for cp in report.missing_core)
        print(f"  ⚠ 核心采分点缺失：{ids}（评级受限）")
    print("-" * 60)
    print(f"  报告：{_short(report_path, 52)}")
    print("=" * 60)


def _short(path: Path, limit: int) -> str:
    text = str(path)
    return text if len(text) <= limit else "…" + text[-(limit - 1):]


if __name__ == "__main__":
    sys.exit(main() or 0)