from contextlib import ExitStack
import io
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import Mock, patch

import run_local_pipeline as session
from workspace_io import read_json


@unittest.skipUnless(sys.platform == "win32", "Windows service-management checks")
class LocalSessionTests(unittest.TestCase):
    def test_default_run_cannot_start_service(self):
        with patch("run_local_pipeline.subprocess.Popen") as start, patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                session.main([])
            start.assert_not_called()

    def test_preexisting_service_is_left_alone(self):
        with patch("run_local_pipeline.sys.platform", "win32"), \
                patch("pathlib.Path.is_file", return_value=True), \
                patch("run_local_pipeline._model_processes", return_value=["ollama.exe"]), \
                patch("run_local_pipeline.subprocess.Popen") as start, \
                patch("run_local_pipeline.subprocess.run") as stop, \
                patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                session.main(["--allow-model"])
            start.assert_not_called()
            stop.assert_not_called()

    def test_low_memory_cannot_start_service(self):
        with patch("run_local_pipeline.sys.platform", "win32"), \
                patch("pathlib.Path.is_file", return_value=True), \
                patch("run_local_pipeline._model_processes", return_value=[]), \
                patch("run_local_pipeline._port_busy", return_value=False), \
                patch("run_local_pipeline._memory_gib", return_value=2), \
                patch("run_local_pipeline.subprocess.Popen") as start, \
                patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                session.main(["--allow-model"])
            start.assert_not_called()

    def test_failure_stops_only_owned_service_and_records_cleanup(self):
        server = Mock(pid=45678)
        server.poll.return_value = None

        def api(path, data=None):
            if path == "/api/version":
                return {"version": "synthetic-test-version"}
            if path == "/api/tags":
                return {"models": []}
            return {}

        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp)
            for name, value in (("ROOT", root), ("sys.platform", "win32")):
                stack.enter_context(patch("run_local_pipeline." + name, value))
            stack.enter_context(patch("pathlib.Path.is_file", return_value=True))
            stack.enter_context(patch("run_local_pipeline._model_processes", return_value=[]))
            stack.enter_context(patch("run_local_pipeline._port_busy", return_value=False))
            stack.enter_context(patch("run_local_pipeline._memory_gib", return_value=6))
            stack.enter_context(patch("run_local_pipeline._api", side_effect=api))
            start = stack.enter_context(patch("run_local_pipeline.subprocess.Popen", return_value=server))
            run = stack.enter_context(patch("run_local_pipeline.subprocess.run"))
            with self.assertRaisesRegex(RuntimeError, "not installed"):
                session.main(["--allow-model"])
            self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "45678", "/T", "/F"])
            environment = start.call_args.kwargs["env"]
            self.assertEqual(environment["CUDA_VISIBLE_DEVICES"], "-1")
            self.assertEqual(environment["OLLAMA_NUM_PARALLEL"], "1")
            record = read_json(root / "evidence" / "local_run.json")
            self.assertEqual(record["result"], "FAILED")
            self.assertTrue(record["cleanup_ok"])
            self.assertEqual(record["stages_completed"], [])


if __name__ == "__main__":
    unittest.main()
