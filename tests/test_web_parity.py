"""The website's JavaScript engine must agree with the Python engine, and the
exported data must match the current Python sources."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import export_web  # noqa: E402


def test_exported_data_is_up_to_date():
    current = json.loads((ROOT / "docs" / "data" / "data.json").read_text())
    fresh = json.loads(json.dumps(export_web.build()))
    assert current == fresh, "docs/data/data.json is stale: run scripts/export_web.py"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_javascript_engine_matches_python(tmp_path):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps(export_web.build_parity_cases()))
    run = subprocess.run(["node", str(ROOT / "tests" / "parity.mjs"), str(cases)], capture_output=True, text=True)
    report = json.loads(run.stdout)
    assert report["total"] > 1000
    assert run.returncode == 0, json.dumps(report["first"], indent=1)
