"""Portable source identities and run snapshots."""

import hashlib
from pathlib import Path
import shutil

from workspace_io import ROOT, read_json, save_json


def digest(path, *, binary=False):
    data = Path(path).read_bytes() if binary else Path(path).read_text(encoding="utf-8-sig").encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def check_preserved_sources():
    manifest = read_json(ROOT / "evidence/integration_sources.json")
    for name, expected in manifest["original_python"].items():
        actual = ROOT / name
        if name == "developer_agent.py":
            saved = ROOT / "evidence/integration_source/developer_agent_original.py"
            if digest(saved) != expected or not actual.read_text(encoding="utf-8").startswith(saved.read_text(encoding="utf-8")):
                raise ValueError("The original Developer code was changed instead of extended.")
        elif digest(actual) != expected:
            raise ValueError(f"Earlier Python source changed: {name}")
    for name, expected in manifest["teacher_files"].items():
        if digest(ROOT / name, binary=True) != expected:
            raise ValueError(f"Teacher file changed: {name}")
    if digest(ROOT / "docs/integration-instructions.pdf", binary=True) != manifest["instructions_sha256"]:
        raise ValueError("The assignment PDF changed.")
    return manifest


def snapshot(folder):
    files = sorted([*ROOT.glob("*.py"), *ROOT.glob("integration/*.py"),
                    *ROOT.glob("integration_tests/*.py")])
    identities = {}
    for source in files:
        relative = source.relative_to(ROOT)
        destination = Path(folder) / "sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        identities[relative.as_posix()] = digest(source)
    save_json(Path(folder) / "source_hashes.json", identities)
    return identities
