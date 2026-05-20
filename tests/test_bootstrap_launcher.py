import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import bootstrap_launcher


def test_find_bootstrap_python_accepts_multi_part_py_launcher(monkeypatch):
    monkeypatch.setattr(bootstrap_launcher.os, "name", "nt")
    monkeypatch.setattr(
        bootstrap_launcher,
        "_candidate_commands",
        lambda: iter(["py -3.11", "python"]),
    )
    monkeypatch.setattr(bootstrap_launcher.shutil, "which", lambda exe: exe)

    seen = []

    def fake_version_ok(command):
        seen.append(command)
        return command == ["py", "-3.11"]

    monkeypatch.setattr(bootstrap_launcher, "_version_ok", fake_version_ok)

    assert bootstrap_launcher._find_bootstrap_python() == ["py", "-3.11"]
    assert seen == [["py", "-3.11"]]


def test_find_bootstrap_python_skips_old_candidate(monkeypatch):
    monkeypatch.setattr(
        bootstrap_launcher,
        "_candidate_commands",
        lambda: iter(["python", "python3.11"]),
    )
    monkeypatch.setattr(bootstrap_launcher.shutil, "which", lambda exe: exe)
    monkeypatch.setattr(
        bootstrap_launcher,
        "_version_ok",
        lambda command: command == ["python3.11"],
    )

    assert bootstrap_launcher._find_bootstrap_python() == ["python3.11"]

