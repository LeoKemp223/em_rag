"""SQLite compatibility helpers.

ChromaDB needs a recent SQLite build. Linux distributions often ship an old
stdlib sqlite3, so we prefer pysqlite3 there when available. On Windows the
pysqlite3-binary wheel is less reliable, and Python 3.11+ usually bundles a
new enough SQLite, so stdlib sqlite3 is the conservative default.
"""

from __future__ import annotations

import platform
import sys


def load_sqlite():
    if platform.system() != "Windows":
        try:
            import pysqlite3 as sqlite3

            sys.modules["sqlite3"] = sqlite3
            return sqlite3
        except ImportError:
            pass

    import sqlite3

    return sqlite3


sqlite3 = load_sqlite()


def sqlite_info() -> dict:
    return {
        "module": sqlite3.__name__,
        "version": sqlite3.sqlite_version,
        "fts5": has_fts5(),
    }


def has_fts5() -> bool:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE fts_check USING fts5(content)")
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()
