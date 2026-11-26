"""
EduEval Web 应用：把命令行评估流程包装成 FastAPI 服务。

用法:
    python web.py                          # http://127.0.0.1:8000
    python web.py --host 0.0.0.0 --port 9000
    uvicorn web:app --reload               # 开发时热重载

约定:
  * 前端是原生 HTML/CSS/JS，全部放 static/，不引入任何前端框架；
  * 评估逻辑复用 edu_eval 包，本文件只做 HTTP 编排、会话存档与视图组装；
  * 会话写入 workspace/<sessionId>/，与命令行版本同一格式，可互相续跑；
  * 提问逐轮揭示：未答完当前问，接口不返回下一问的文本，避免“先看三问再组织答案”。
"""
from __future__ import annotations

import argparse
import json
import re
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from edu_eval.assets import draw_question, list_questions, load_question
from edu_eval.config import config, path_config
from edu_eval.llm import LLMClient, LLMError
from edu_eval.logs import setup_logging
from edu_eval.models import (
    CheckpointResult, GeneratedQuestion, QAPair, Question, Report, ScoreItem,
)
from edu_eval.qa_gen import generate_questions
from edu_eval.reporter import render_report
from edu_eval.scorer import make_rating, score_all

STATIC = Path(__file__).resolve().parent / "static"
ROUND_SUFFIX = re.compile(r"·R(\d+)$")
SESSION_ID = re.compile(r"^EV-[0-9A-Za-z\-]+$")

setup_logging()  # uvicorn web:app 不经过 main()，这里初始化一次

app = FastAPI(title="EduEval", description="初中数学讲题教学能力评估", version="0.1.0")


# ---------------------------------------------------------------- 会话状态

class Session:
    """一次评估的进程内状态；每一步都同步落盘到 workspace/<id>/。"""

    def __init__(
        self,
        session_id: str,
        question: Question,
        lecture: str,
        candidate_id: str,
        dry_run: bool,
    ):
        self.id = session_id
        self.question = question
        self.lecture = lecture
        self.candidate_id = candidate_id
        self.dry_run = dry_run
        self.questions: list[GeneratedQuestion] = []
        self.answers: dict[int, str] = {}
        self.status = "answering"          # answering / scored
        self.report_payload: dict | None = None
        self.markdown = ""
        self.lock = threading.Lock()


_sessions: dict[str, Session] = {}
_sessions_lock = threading.Lock()


def make_session_id() -> str:
    """生成不冲突的会话编号（同秒多次提交时追加序号）。"""
    base = "EV-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate, n = base, 1
    while (path_config()["workspace"] / candidate / "session.json").exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def get_session(session_id: str) -> Session:
    """取会话：优先内存，其次从磁盘恢复（服务重启后仍可续看/续评）。"""
    if not SESSION_ID.match(session_id):
        raise HTTPException(status_code=400, detail="非法的会话编号")

    with _sessions_lock:
        session = _sessions.get(session_id)
    if session is None:
        session = _load_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"会话不存在：{session_id}")
        with _sessions_lock:
            _sessions[session_id] = session
    return session


def _load_session(session_id: str) -> Session | None:
    """从 workspace/<id>/session.json 恢复会话。"""
    session_dir = path_config()["workspace"] / session_id
    meta_file = session_dir / "session.json"
    if not meta_file.exists():
        return None

    raw = json.loads(meta_file.read_text(encoding="utf-8-sig"))
    try:
        question = load_question(raw["questionId"])
    except (KeyError, FileNotFoundError):
        return None

    session = Session(
        session_id=session_id,
        question=question,
        lecture=raw.get("lecture", ""),
        candidate_id=raw.get("candidateId", ""),
        dry_run=bool(raw.get("meta", {}).get("dry_run", False)),
    )
    for item in raw.get("qa", []):
        session.questions.append(
            GeneratedQuestion(
                round=int(item["round"]),
                persona_id=item.get("personaId", ""),
                persona_name=item.get("personaName", ""),
                text=item.get("questionText", ""),
                reference_points=list(item.get("referencePoints", [])),
            )
        )
    session.answers = {
        int(item["round"]): item["answer"]
        for item in raw.get("qa", [])
        if item.get("answer")
    }
    session.status = raw.get("status", "answering")
    session.report_payload = raw.get("report")

    report_file = session_dir / "report.md"
    if report_file.exists():
        session.markdown = report_file.read_text(encoding="utf-8")
    return session


def _persist(session: Session) -> None:
    """落盘：与命令行版本同一份 session.json，可被 `python run.py run --session` 续跑。"""
    session_dir = path_config()["workspace"] / session.id
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "sessionId": session.id,
        "questionId": session.question.id,
        "candidateId": session.candidate_id,
        "lecture": session.lecture,
        "status": session.status,
        "qa": [
            {
                "round": q.round,
                "personaId": q.persona_id,
                "personaName": q.persona_name,
                "questionText": q.text,
                "referencePoints": q.reference_points,
                "answer": session.answers.get(q.round, ""),
            }
            for q in session.questions
        ],
        "meta": {
            "dry_run": session.dry_run,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
    }
    if session.report_payload:
        payload["rating"] = session.report_payload["rating"]
        payload["report"] = session.report_payload
    (session_dir / "session.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------- 视图组装

def _question_view(question: Question) -> dict:
    return {
        "id": question.id,
        "title": question.title,
        "grade": question.grade,
        "task": question.task,
        "checkpointCount": len(question.checkpoints),
        "coreCount": len(question.core_checkpoints),
        "pitfallCount": len(question.pitfalls),
    }


def _score_view(item: ScoreItem) -> dict:
    return {
        "dimension": ROUND_SUFFIX.sub("", item.dimension),
        "name": item.name,
        "score": round(float(item.score), 1),
        "rationale": item.rationale,
        "evidence": item.evidence,
    }


def _checkpoint_view(item: CheckpointResult) -> dict:
    return {
        "id": item.checkpoint_id,
        "description": item.description,
        "status": item.status,
        "isCore": item.is_core,
        "evidence": item.evidence,
    }


def _session_detail(session: Session) -> dict:
    """
    会话视图。

    注意：只揭示到「当前待答」这一问，后面问题的题干与参考要点不下发——
    否则前端可以先看到三问再统一作答，「逐轮揭示」就失效了。
    """
    answered = set(session.answers)
    # 揭示到「已答最大轮次 + 1」：当前待答的一问可见，后面的仍隐藏
    revealed_until = max(answered) + 1 if answered else 1
    questions = []
    for q in session.questions:
        revealed = q.round <= revealed_until
        questions.append({
            "round": q.round,
            "personaName": q.persona_name,
            "revealed": revealed,
            "text": q.text if revealed else "",
            "answer": session.answers.get(q.round, ""),
        })
    return {
        "sessionId": session.id,
        "status": session.status,
        "candidateId": session.candidate_id,
        "dryRun": session.dry_run,
        "question": _question_view(session.question),
        "lectureWords": len(session.lecture),
        "questions": questions,
        "answeredRounds": sorted(answered),
        "report": session.report_payload,
    }


def _report_payload(report: Report) -> dict:
    """把 Report 转成前端直接可渲染的结构（顺便按轮次分组问答得分）。"""
    grouped: dict[int, list[dict]] = {}
    for item in report.qa_scores:
        match = ROUND_SUFFIX.search(item.dimension)
        round_no = int(match.group(1)) if match else 0
        grouped.setdefault(round_no, []).append(_score_view(item))

    qa_rounds = []
    for pair in report.qa_pairs:
        qa_rounds.append({
            "round": pair.question.round,
            "personaName": pair.question.persona_name,
            "question": pair.question.text,
            "answer": pair.answer,
            "scores": grouped.get(pair.question.round, []),
        })

    return {
        "sessionId": report.session_id,
        "rating": report.rating,
        "question": _question_view(report.question),
        "generalAvg": round(report.general_avg, 2),
        "qaAvg": round(report.qa_avg, 2),
        "covered": report.covered_count,
        "totalCheckpoints": report.total_checkpoints,
        "missingCore": [cp.checkpoint_id for cp in report.missing_core],
        "general": [_score_view(item) for item in report.general_scores],
        "checkpoints": [_checkpoint_view(item) for item in report.checkpoints],
        "qa": qa_rounds,
        "suggestions": report.suggestions,
        "meta": report.meta,
    }


# ---------------------------------------------------------------- 请求体

class CreateSessionRequest(BaseModel):
    """提交讲稿，开始一次评估。"""

    questionId: str | None = None     # None = 由服务端随机抽题
    lecture: str
    candidateId: str = "web-user"
    dryRun: bool | None = None       # None = 没配密钥时自动走桩数据
    seed: int | None = None


class AnswerRequest(BaseModel):
    """提交某一轮的回答。"""

    round: int
    answer: str


# ---------------------------------------------------------------- 前端

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------------------------------------------------------------- API

@app.get("/api/config")
def api_config() -> dict:
    """前端启动时取一次：模型信息、字数下限、是否可直连真实模型。"""
    has_key = bool(config["llm"]["api_key"])
    return {
        "model": config["llm"]["model"],
        "hasKey": has_key,
        "dryRunDefault": not has_key,
        "rounds": config["qa"]["rounds"],
        "minScriptWords": config["limits"]["min_script_words"],
        "minAnswerWords": config["limits"]["min_answer_words"],
    }


@app.get("/api/questions")
def api_questions() -> dict:
    """题库清单（只给元信息，不含采分点内容）。"""
    return {"questions": [_question_view(q) for q in list_questions()]}


@app.get("/api/draw")
def api_draw(questionId: str = "") -> dict:
    """
    抽题：不传 questionId 时随机抽一道；传了则按 ID 取（用于刷新页面后恢复）。

    抽题只给题面（标题/学段/任务），不给采分点，也不给任何学生人设。
    """
    pool = list_questions()
    if not pool:
        raise HTTPException(status_code=503, detail="题库为空，无法抽题")

    if questionId:
        try:
            question = load_question(questionId)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"question": _question_view(question), "poolSize": len(pool), "random": False}

    try:
        question = draw_question()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"question": _question_view(question), "poolSize": len(pool), "random": True}


@app.post("/api/sessions", status_code=201)
def api_create_session(req: CreateSessionRequest) -> dict:
    """提交讲稿 → 抽人设 → 生成 3 问（只返回第 1 问）。"""
    lecture = (req.lecture or "").strip()
    min_words = config["limits"]["min_script_words"]
    if len(lecture) < min_words:
        raise HTTPException(
            status_code=422,
            detail=f"讲稿仅 {len(lecture)} 字，低于下限 {min_words} 字",
        )

    if req.questionId:
        try:
            question = load_question(req.questionId)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        # 客户端没带题目就现抽一道：抽题永远是系统行为，不给被试挑
        try:
            question = draw_question(req.seed)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    dry_run = req.dryRun if req.dryRun is not None else not bool(config["llm"]["api_key"])
    try:
        client = LLMClient(dry_run=dry_run)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        questions = generate_questions(question, lecture, client, seed=req.seed)
    except (LLMError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"提问生成失败：{exc}") from exc

    session = Session(
        session_id=make_session_id(),
        question=question,
        lecture=lecture,
        candidate_id=(req.candidateId or "web-user").strip(),
        dry_run=dry_run,
    )
    session.questions = questions

    with _sessions_lock:
        _sessions[session.id] = session
    _persist(session)
    return _session_detail(session)


@app.get("/api/sessions/{session_id}")
def api_get_session(session_id: str) -> dict:
    """取会话状态（刷新页面后可凭 localStorage 里的编号恢复）。"""
    return _session_detail(get_session(session_id))


@app.post("/api/sessions/{session_id}/answers")
def api_submit_answer(session_id: str, req: AnswerRequest) -> dict:
    """提交一轮回答；提交后下一问题才被揭示。"""
    session = get_session(session_id)
    with session.lock:
        if session.status == "scored":
            raise HTTPException(status_code=409, detail="已生成报告，不能再修改回答")

        target = next((q for q in session.questions if q.round == req.round), None)
        if target is None:
            raise HTTPException(status_code=404, detail=f"没有第 {req.round} 轮提问")

        # 必须按序作答：前面还有没答的轮次就拒绝，避免「跳着答」破坏逐轮揭示
        earlier = [
            q.round
            for q in session.questions
            if q.round < req.round and q.round not in session.answers
        ]
        if earlier:
            raise HTTPException(status_code=409, detail=f"请先回答第 {earlier[0]} 轮")

        answer = (req.answer or "").strip()
        min_words = config["limits"]["min_answer_words"]
        if len(answer) < min_words:
            raise HTTPException(
                status_code=422,
                detail=f"回答仅 {len(answer)} 字，低于下限 {min_words} 字",
            )

        session.answers[req.round] = answer
        _persist(session)
    return _session_detail(session)


@app.post("/api/sessions/{session_id}/score")
def api_score(session_id: str) -> dict:
    """全部答完后评分并出报告（已评过的直接返回，可重复调用）。"""
    session = get_session(session_id)
    with session.lock:
        if session.report_payload:
            return session.report_payload

        missing = [q.round for q in session.questions if q.round not in session.answers]
        if missing:
            raise HTTPException(
                status_code=409,
                detail=f"还有 {len(missing)} 轮未作答：第 {'、'.join(map(str, missing))} 轮",
            )

        pairs = [
            QAPair(question=q, answer=session.answers[q.round])
            for q in session.questions
        ]
        try:
            client = LLMClient(dry_run=session.dry_run)
        except LLMError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        try:
            general, qa_scores, checkpoints, suggestions = score_all(
                session.question, session.lecture, pairs, client
            )
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=f"评分失败：{exc}") from exc

        report = Report(
            session_id=session.id,
            question=session.question,
            lecture=session.lecture,
            qa_pairs=pairs,
            general_scores=general,
            qa_scores=qa_scores,
            checkpoints=checkpoints,
            suggestions=suggestions,
            meta={
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "model": "dry-run" if session.dry_run else config["llm"]["model"],
                "samples": 1,
                "dry_run": session.dry_run,
                **client.stats(),
            },
        )
        report.rating = make_rating(report)

        session.report_payload = _report_payload(report)
        session.markdown = render_report(report)
        session.status = "scored"

        session_dir = path_config()["workspace"] / session.id
        (session_dir / "report.md").write_text(session.markdown, encoding="utf-8")
        _persist(session)
    return session.report_payload


@app.get("/api/sessions/{session_id}/report.md", response_class=PlainTextResponse)
def api_report_markdown(session_id: str) -> PlainTextResponse:
    """下载 Markdown 报告（与命令行产物完全一致）。"""
    session = get_session(session_id)
    if not session.markdown:
        raise HTTPException(status_code=409, detail="尚未生成报告")
    return PlainTextResponse(session.markdown, media_type="text/markdown; charset=utf-8")


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------- 启动

def main() -> int:
    """本地启动：python web.py [--host] [--port] [--reload]。"""
    parser = argparse.ArgumentParser(
        prog="edu_eval_web",
        description="EduEval Web 服务（FastAPI）",
    )
    parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址（str）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（int）")
    parser.add_argument("--reload", action="store_true", help="代码变更自动重载（bool）")
    args = parser.parse_args()

    import uvicorn

    if args.reload:
        uvicorn.run("web:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())