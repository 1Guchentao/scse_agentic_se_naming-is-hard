import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

import developer_agent
import inspect_results
import local_qwen
import planner_agent
from tests.test_agents import PLAN, REQUIREMENTS, SOURCE
from workspace_io import read_json, save_json, save_text


OPTIONS = {"num_gpu": 0, "num_thread": 2, "num_ctx": 2048, "num_predict": 768, "temperature": 0}


def exchange(stage, context, output, prompt):
    return {
        "stage": stage,
        "request": {
            "model": local_qwen.MODEL, "stream": False, "keep_alive": 0, "options": OPTIONS.copy(),
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(context)}],
        },
        "response": {"done": True, "done_reason": "stop", "message": {"content": output}},
    }


class TransportTests(unittest.TestCase):
    def _opener(self, payload):
        response = Mock()
        response.read.return_value = json.dumps(payload).encode()
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        return opener

    def test_cpu_limits_proxy_bypass_and_original_exchange_recorded(self):
        response = {"done": True, "done_reason": "stop", "message": {"content": "exact\ntext"}}
        opener = self._opener(response)
        with tempfile.TemporaryDirectory() as temp, patch("local_qwen.build_opener", return_value=opener) as build:
            result = local_qwen.ask("planner", "instructions", REQUIREMENTS,
                                    response_shape="json", trace_folder=temp)
            self.assertEqual(result, "exact\ntext")
            self.assertEqual(build.call_args.args[0].proxies, {})
            payload = json.loads(opener.open.call_args.args[0].data)
            self.assertEqual(payload["options"], OPTIONS)
            self.assertEqual(payload["keep_alive"], 0)
            self.assertEqual(payload["format"], "json")
            self.assertEqual(len(payload["messages"]), 2)
            self.assertEqual(json.loads(payload["messages"][1]["content"]), REQUIREMENTS)
            record = read_json(next(Path(temp).glob("*.json")))
            self.assertEqual(record["response"], response)

    def test_truncated_reply_recorded_but_rejected(self):
        response = {"done": True, "done_reason": "length", "message": {"content": "unfinished"}}
        with tempfile.TemporaryDirectory() as temp, patch("local_qwen.build_opener", return_value=self._opener(response)):
            with self.assertRaises(ValueError):
                local_qwen.ask("developer", "instructions", PLAN, trace_folder=temp)
            self.assertEqual(read_json(next(Path(temp).glob("*.json")))["response"], response)

    def test_empty_or_incomplete_responses_rejected(self):
        for response in ({}, [], {"done": False}, {"done": True, "message": {"content": " "}}):
            with self.subTest(response=response), patch("local_qwen.build_opener", return_value=self._opener(response)):
                with self.assertRaises(ValueError):
                    local_qwen.ask("planner", "instructions", REQUIREMENTS)

    def test_transport_failure_is_not_retried(self):
        opener = Mock()
        opener.open.side_effect = URLError("offline")
        with patch("local_qwen.build_opener", return_value=opener):
            with self.assertRaises(RuntimeError):
                local_qwen.ask("planner", "instructions", REQUIREMENTS)
        self.assertEqual(opener.open.call_count, 1)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        save_text(self.root / "brief.txt", "Synthetic test brief.\n")
        save_json(self.root / "artifacts" / "requirements.json", REQUIREMENTS)
        save_json(self.root / "artifacts" / "plan.json", PLAN)
        save_text(self.root / "navigation_logic.py", SOURCE)
        self.planner_path = self.root / "evidence" / "exchanges" / "planner-fixture.json"
        self.developer_path = self.root / "evidence" / "exchanges" / "developer-fixture.json"
        self.planner = exchange("planner", REQUIREMENTS, json.dumps(PLAN), planner_agent.INSTRUCTIONS)
        self.developer = exchange("developer", PLAN, SOURCE, developer_agent.INSTRUCTIONS)
        save_json(self.planner_path, self.planner)
        save_json(self.developer_path, self.developer)

    def test_full_evidence_chain(self):
        report = inspect_results.inspect(self.root)
        self.assertEqual(report["navigation_cases"], 32)
        self.assertEqual(report["result"], "PASS")

    def test_missing_exchange_is_not_treated_as_real_generation(self):
        self.developer_path.unlink()
        with self.assertRaises(ValueError):
            inspect_results.inspect(self.root)

    def test_modified_output_without_matching_exchange_rejected(self):
        save_text(self.root / "navigation_logic.py", SOURCE + "\n")
        with self.assertRaises(ValueError):
            inspect_results.inspect(self.root)

    def test_mismatched_input_extra_history_or_gpu_request_rejected(self):
        records = []
        different_input = copy.deepcopy(self.developer)
        different_input["request"]["messages"][1]["content"] = "{}"
        records.append(different_input)
        extra_history = copy.deepcopy(self.developer)
        extra_history["request"]["messages"].append({"role": "assistant", "content": "old chat"})
        records.append(extra_history)
        gpu_request = copy.deepcopy(self.developer)
        gpu_request["request"]["options"]["num_gpu"] = 1
        records.append(gpu_request)
        for record in records:
            save_json(self.developer_path, record)
            with self.assertRaises(ValueError):
                inspect_results.inspect(self.root)

    def test_crlf_checkout_does_not_change_artifact_identity(self):
        path = self.root / "navigation_logic.py"
        original = inspect_results.text_digest(path)
        path.write_bytes(SOURCE.replace("\n", "\r\n").encode())
        self.assertEqual(inspect_results.text_digest(path), original)
        self.assertEqual(inspect_results.inspect(self.root)["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
