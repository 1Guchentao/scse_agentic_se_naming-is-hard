import json
from pathlib import Path
import navigation_under_test

def pytest_sessionfinish(session, exitstatus):
    Path("calls.json").write_text(json.dumps(navigation_under_test.recorded_states), encoding="utf-8")
