import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sqlite_compat import sqlite_info


def test_sqlite_info_reports_version_and_fts5():
    info = sqlite_info()

    assert info["module"]
    assert info["version"]
    assert isinstance(info["fts5"], bool)
