import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from edu_eval.assets import load_question
from edu_eval.llm import LLMClient, LLMError
from edu_eval.models import QAPair
from edu_eval.qa_gen import generate_questions
from edu_eval.scorer import score_all
from edu_eval.session_store import reserve_session, write_snapshot


class AssessmentIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.client = LLMClient(dry_run=True)
        self.question = load_question("M-CZ-001")
        self.lecture = "讲稿" * 300
        self.questions = generate_questions(self.question, self.lecture, self.client)

    def test_malformed_scores_never_produce_a_rating(self):
        pairs = [QAPair(q, "回答") for q in self.questions]
        original = self.client.chat_json
        for task, corrupt in (
            ("score_general", lambda d: d["dimensions"].pop()),
            ("score_general", lambda d: d["dimensions"][0].pop("score")),
            ("score_general", lambda d: d["dimensions"][0].update(score="NaN")),
            ("score_checkpoint", lambda d: d["checkpoints"].pop()),
            ("score_checkpoint", lambda d: d["checkpoints"][0].update(status="未知")),
            ("score_qa", lambda d: d["rounds"].pop()),
            ("score_qa", lambda d: d["rounds"][0]["scores"][0].update(dimension="Q3")),
        ):
            def reply(prompt, temperature, task):
                data = original(prompt, temperature, task)
                if task == target:
                    corrupt(data)
                return data

            target = task
            with self.subTest(task=task), patch.object(self.client, "chat_json", reply):
                with self.assertRaises(LLMError):
                    score_all(self.question, self.lecture, pairs, self.client)

    def test_incomplete_rounds_fail_after_retries(self):
        data = self.client.chat_json("", task="qa_generation")
        data["questions"].pop()
        with patch.object(self.client, "chat_json", return_value=data) as chat:
            with self.assertRaises(RuntimeError):
                generate_questions(self.question, self.lecture, self.client)
            self.assertEqual(chat.call_count, 3)

    def test_concurrent_sessions_get_distinct_directories(self):
        with TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=8) as workers:
            directories = list(workers.map(reserve_session, [Path(tmp)] * 24))
            self.assertEqual(len(set(directories)), 24)
            self.assertTrue(all(directory.is_dir() for directory in directories))

    def test_failed_save_preserves_previous_snapshot(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            write_snapshot(path, '{"round": 1}')
            with patch.object(Path, "replace", side_effect=OSError):
                with self.assertRaises(OSError):
                    write_snapshot(path, '{"round": 2}')
            self.assertEqual(json.loads(path.read_text()), {"round": 1})
            self.assertEqual(list(path.parent.iterdir()), [path])
