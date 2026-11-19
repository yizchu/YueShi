"""
Web 层测试：用 FastAPI TestClient 跑通「提交讲稿 → 逐轮问答 → 报告」。

全部走 dry-run 桩数据，不访问网络。
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import web
from edu_eval.config import config


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """把 workspace 指到临时目录，测试之间互不干扰。"""
    monkeypatch.setitem(config["paths"], "workspace", str(tmp_path))
    web._sessions.clear()
    return TestClient(web.app)


def _lecture() -> str:
    path = Path("datasets/examples/M-CZ-001-高质量讲稿.md")
    return path.read_text(encoding="utf-8-sig")


def test_config_and_questions(client: TestClient):
    cfg = client.get("/api/config").json()
    assert cfg["rounds"] == 3
    assert isinstance(cfg["hasKey"], bool)
    assert cfg["minScriptWords"] > 0

    questions = client.get("/api/questions").json()["questions"]
    assert questions
    assert {"id", "title", "grade", "checkpointCount"} <= set(questions[0])


def test_home_and_static(client: TestClient):
    home = client.get("/")
    assert home.status_code == 200
    assert "EduEval" in home.text
    assert home.headers["cache-control"] == "no-cache"

    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_draw_question(client: TestClient):
    """抽题是系统行为：不传 ID 时随机抽，传了 ID 只用于恢复。"""
    drawn = client.get("/api/draw").json()
    assert drawn["random"] is True
    assert drawn["poolSize"] >= 1
    assert drawn["question"]["id"]
    # 只给题面元信息，不能泄露采分点
    assert "checkpoints" not in drawn["question"]
    assert "task" in drawn["question"]

    fixed = client.get("/api/draw", params={"questionId": "M-CZ-001"}).json()
    assert fixed["random"] is False
    assert fixed["question"]["id"] == "M-CZ-001"

    missing = client.get("/api/draw", params={"questionId": "NOT-EXIST"})
    assert missing.status_code == 404

    # 客户端不带题目时，服务端现抽一道
    created = client.post("/api/sessions", json={
        "lecture": _lecture(), "dryRun": True,
    })
    assert created.status_code == 201, created.text
    assert created.json()["sessionId"]


def test_empty_pool(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(web, "list_questions", lambda: [])
    assert client.get("/api/draw").status_code == 503


def test_full_flow(client: TestClient):
    created = client.post("/api/sessions", json={
        "questionId": "M-CZ-001",
        "lecture": _lecture(),
        "dryRun": True,
    })
    assert created.status_code == 201, created.text
    session = created.json()
    session_id = session["sessionId"]

    # 只揭示第 1 问
    assert session["questions"][0]["revealed"] is True
    assert session["questions"][0]["text"]
    assert session["questions"][1]["revealed"] is False
    assert session["questions"][1]["text"] == ""

    # 答完第 1 问后，第 2 问才揭示
    step = client.post(f"/api/sessions/{session_id}/answers",
                       json={"round": 1, "answer": "回答" * 40})
    assert step.status_code == 200, step.text
    data = step.json()
    assert data["questions"][1]["revealed"] is True
    assert data["questions"][1]["text"]
    assert data["questions"][2]["revealed"] is False

    # 还剩两轮时不能评分
    early = client.post(f"/api/sessions/{session_id}/score")
    assert early.status_code == 409

    for rnd in (2, 3):
        resp = client.post(f"/api/sessions/{session_id}/answers",
                           json={"round": rnd, "answer": "回答" * 40})
        assert resp.status_code == 200, resp.text
    assert len(resp.json()["answeredRounds"]) == 3

    report = client.post(f"/api/sessions/{session_id}/score")
    assert report.status_code == 200, report.text
    payload = report.json()
    assert payload["rating"]
    assert len(payload["general"]) == 3
    assert payload["totalCheckpoints"] > 0
    assert len(payload["qa"]) == 3
    assert all(len(round_["scores"]) == 3 for round_ in payload["qa"])

    # 评分幂等
    again = client.post(f"/api/sessions/{session_id}/score")
    assert again.json()["rating"] == payload["rating"]

    markdown = client.get(f"/api/sessions/{session_id}/report.md")
    assert markdown.status_code == 200
    assert "评估报告" in markdown.text


def test_validation(client: TestClient):
    short = client.post("/api/sessions", json={
        "questionId": "M-CZ-001", "lecture": "太短", "dryRun": True,
    })
    assert short.status_code == 422

    missing = client.post("/api/sessions", json={
        "questionId": "NOT-EXIST", "lecture": _lecture(), "dryRun": True,
    })
    assert missing.status_code == 404

    created = client.post("/api/sessions", json={
        "questionId": "M-CZ-001", "lecture": _lecture(), "dryRun": True,
    }).json()
    sid = created["sessionId"]

    tiny = client.post(f"/api/sessions/{sid}/answers",
                       json={"round": 1, "answer": "嗯"})
    assert tiny.status_code == 422

    unknown_round = client.post(f"/api/sessions/{sid}/answers",
                                json={"round": 9, "answer": "回答" * 40})
    assert unknown_round.status_code == 404

    # 不能跳着答：未答第 1 轮就提交第 2 轮
    out_of_order = client.post(f"/api/sessions/{sid}/answers",
                               json={"round": 2, "answer": "回答" * 40})
    assert out_of_order.status_code == 409


def test_session_persisted_to_disk(client: TestClient, tmp_path: Path):
    created = client.post("/api/sessions", json={
        "questionId": "M-CZ-001", "lecture": _lecture(), "dryRun": True,
    }).json()
    meta_file = tmp_path / created["sessionId"] / "session.json"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta["questionId"] == "M-CZ-001"
    assert len(meta["qa"]) == 3

    # 服务重启后（内存清空）仍能恢复
    web._sessions.clear()
    recovered = client.get(f"/api/sessions/{created['sessionId']}")
    assert recovered.status_code == 200
    assert recovered.json()["sessionId"] == created["sessionId"]


def test_bad_session_id(client: TestClient):
    assert client.get("/api/sessions/BAD-ID").status_code == 400
    assert client.get("/api/sessions/EV-20990101-000000").status_code == 404