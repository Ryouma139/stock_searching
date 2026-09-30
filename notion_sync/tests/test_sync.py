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


# ---------------------------------------------------------- ページ内の表

def cell(text):
    return [{"plain_text": text}] if text else []


def table_row(rid, *texts, edited="2026-09-15T00:00:00.000Z"):
    return {"id": rid, "type": "table_row", "last_edited_time": edited,
            "table_row": {"cells": [cell(t) for t in texts]}}


class FakePageNotion(FakeNotion):
    """見出し + シンプルテーブル + トグル内のインライン DB を含むページ。"""

    def __init__(self):
        super().__init__([page("p1", "安川電機", "2026-09-15T01:00:00.000Z", price=5000)])
        self.rows = [
            table_row("r0", "銘柄", "コード", "株価", ""),
            table_row("r1", "安川電機", "6506", "5000", "メモ1"),
            table_row("r2", "アスア", "246A", "1200", None),
        ]
        self.blocks = {
            "PAGE": [
                {"id": "h", "type": "heading_2", "has_children": False,
                 "heading_2": {"rich_text": cell("監視銘柄一覧")}},
                {"id": "T1", "type": "table", "has_children": True,
                 "table": {"table_width": 4, "has_column_header": True, "has_row_header": False}},
                {"id": "tg", "type": "toggle", "has_children": True, "toggle": {"rich_text": cell("詳細")}},
            ],
            "tg": [{"id": DB_ID, "type": "child_database", "has_children": False,
                    "child_database": {"title": "株ウォッチ DB"}}],
        }

    def get_page(self, page_id):
        return {"properties": {"Name": {"type": "title", "title": cell("株まとめ")}}}

    def get_block_children(self, block_id):
        return iter(self.rows if block_id == "T1" else self.blocks.get(block_id, []))


def test_page_with_simple_table_and_inline_db(conn):
    notion = FakePageNotion()
    assert sync.sync_page(notion, conn, SCHEMA, "PAGE", full=False) == 0

    assert conn.execute(
        f'SELECT _row_id, _row_index, "銘柄", "コード", "株価", col_4, _archived '
        f'FROM {SCHEMA}."監視銘柄一覧" ORDER BY _row_index').fetchall() == [
        ("r1", 0, "安川電機", "6506", "5000", "メモ1", False),
        ("r2", 1, "アスア", "246A", "1200", None, False),
    ]
    assert conn.execute(f'SELECT "銘柄名" FROM {SCHEMA}."株ウォッチ_db"').fetchall() == [("安川電機",)]

    # 行の削除 + ヘッダー名の変更 → 旧行は archived、新しい列名のカラムが追加される
    notion.rows = [table_row("r0", "銘柄", "証券コード", "株価", ""), table_row("r2", "アスア", "246A", "1300", None)]
    assert sync.sync_page(notion, conn, SCHEMA, "PAGE", full=False) == 0
    assert conn.execute(
        f'SELECT _row_id, "証券コード", "株価", _archived FROM {SCHEMA}."監視銘柄一覧" ORDER BY _row_id').fetchall() == [
        ("r1", None, "5000", True),
        ("r2", "246A", "1300", False),
    ]


def test_simple_table_without_header():
    cols = sync.build_simple_table_columns(None, 3)
    assert cols == {0: ("col_1", "text"), 1: ("col_2", "text"), 2: ("col_3", "text")}
    dup = sync.build_simple_table_columns([cell("a"), cell("a"), cell("_row_id")], 3)
    assert [c for c, _ in dup.values()] == ["a", "a_2", "_row_id_2"]


def test_parse_targets_accepts_urls():
    url = "https://www.notion.so/ws/My-Page-0123456789abcdef0123456789abcdef?v=1"
    assert sync.parse_targets(f"{url}, {url}:stocks") == [
        ("0123456789abcdef0123456789abcdef", None),
        ("0123456789abcdef0123456789abcdef", "stocks"),
    ]
