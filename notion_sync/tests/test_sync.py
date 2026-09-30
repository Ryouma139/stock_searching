"""PostgreSQL を使った sync.py の結合テスト。

TEST_DATABASE_URL に空の検証用 DB を指定して実行する:
  TEST_DATABASE_URL=postgresql://postgres@localhost/postgres python -m pytest notion_sync/tests
"""

import os
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sync  # noqa: E402

DB_ID = "11111111-2222-3333-4444-555555555555"
SCHEMA = "notion_test"


def page(pid, name, edited, **extra):
    props = {
        "銘柄名": {"type": "title", "title": [{"plain_text": name}]},
        "株価": {"type": "number", "number": extra.get("price")},
        "タグ": {"type": "multi_select", "multi_select": [{"name": t} for t in extra.get("tags", [])]},
        "取得日": {"type": "date", "date": {"start": "2026-09-15", "end": None}},
        "監視中": {"type": "checkbox", "checkbox": extra.get("watch", False)},
    }
    return {"id": pid, "url": f"https://notion.so/{pid}", "created_time": "2026-09-01T00:00:00.000Z",
            "last_edited_time": edited, "archived": False, "properties": props}


class FakeNotion:
    def __init__(self, pages, schema_extra=None):
        self.pages = pages
        self.schema = {k: {"type": v["type"]} for k, v in pages[0]["properties"].items()}
        self.schema.update(schema_extra or {})
        self.last_since = "unset"

    def get_database(self, database_id):
        return {"title": [{"plain_text": "株ウォッチ DB"}], "properties": self.schema}

    def query_pages(self, database_id, edited_since=None):
        self.last_since = edited_since
        return iter(self.pages)


@pytest.fixture
def conn():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL が未設定")
    with psycopg.connect(url) as c:
        c.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        sync.ensure_meta(c, SCHEMA)
        c.commit()
        yield c
        c.rollback()
        c.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        c.commit()


def rows(conn, table):
    return conn.execute(
        f'SELECT _page_id, "銘柄名", "株価", "タグ", "取得日"::date::text, "監視中", _archived '
        f'FROM {SCHEMA}."{table}" ORDER BY _page_id').fetchall()


def test_full_then_incremental_then_delete(conn):
    notion = FakeNotion([
        page("a", "安川電機", "2026-09-15T01:00:00.000Z", price=5000, tags=["ロボット"], watch=True),
        page("b", "アスア", "2026-09-15T02:00:00.000Z", price=1200),
    ])
    sync.sync_database(notion, conn, SCHEMA, DB_ID, None, full=False)
    table = "株ウォッチ_db"
    assert notion.last_since is None  # 初回は全件
    assert rows(conn, table) == [
        ("a", "安川電機", 5000, ["ロボット"], "2026-09-15", True, False),
        ("b", "アスア", 1200, [], "2026-09-15", False, False),
    ]

    # 差分: b だけ更新 + 新しいプロパティ追加
    notion.pages = [page("b", "アスア", "2026-09-16T00:00:00.000Z", price=1300)]
    notion.pages[0]["properties"]["メモ"] = {"type": "rich_text", "rich_text": [{"plain_text": "急騰"}]}
    notion.schema["メモ"] = {"type": "rich_text"}
    sync.sync_database(notion, conn, SCHEMA, DB_ID, None, full=False)
    assert notion.last_since is not None
    assert conn.execute(f'SELECT "株価", "メモ" FROM {SCHEMA}."{table}" WHERE _page_id = %s', ("b",)).fetchone() \
        == (1300, "急騰")
    assert conn.execute(f'SELECT count(*) FROM {SCHEMA}."{table}" WHERE NOT _archived').fetchone()[0] == 2

    # full: a が Notion から消えた → archived
    sync.sync_database(notion, conn, SCHEMA, DB_ID, None, full=True)
    assert conn.execute(f'SELECT _page_id FROM {SCHEMA}."{table}" WHERE _archived').fetchall() == [("a",)]


def test_type_change_is_skipped_not_fatal(conn):
    notion = FakeNotion([page("a", "X", "2026-09-15T01:00:00.000Z", price=1)])
    sync.sync_database(notion, conn, SCHEMA, DB_ID, "stocks", full=True)
    notion.schema["株価"] = {"type": "rich_text"}
    notion.pages[0]["properties"]["株価"] = {"type": "rich_text", "rich_text": [{"plain_text": "高い"}]}
    sync.sync_database(notion, conn, SCHEMA, DB_ID, None, full=True)
    raw = conn.execute(f"SELECT _properties->'株価'->'rich_text'->0->>'plain_text' FROM {SCHEMA}.stocks").fetchone()
    assert raw == ("高い",)


def test_long_japanese_names_fit_identifier_limit():
    cols = sync.build_column_map({"あ" * 30: {"type": "title"}, "あ" * 31: {"type": "number"}})
    names = [c for c, _ in cols.values()]
    assert len(set(names)) == 2
    assert all(len(n.encode()) <= 63 for n in names)


def test_parse_targets():
    assert sync.parse_targets("abc, def:stocks ,") == [("abc", None), ("def", "stocks")]
