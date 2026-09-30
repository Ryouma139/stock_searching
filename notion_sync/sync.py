"""Notion データベース → PostgreSQL 同期スクリプト。

Notion の表 1 つにつき PostgreSQL のテーブルを 1 つ用意し、表の各行を 1 レコードとして
UPSERT する。テーブルとカラムは Notion の列（プロパティ／ヘッダー行）から自動で作成・追加される。

対象の指定方法は 2 通り:
  - ページ指定: ページ内にある表を自動で探して同期する
      * インラインデータベース（/database で作った表） … 列の型を保って同期、差分同期に対応
      * シンプルテーブル（/table で作った表）           … 1 行目をヘッダーとして全列 text で同期
  - データベース指定: データベースを直接同期する

  - 通常実行: 前回同期以降に更新されたページだけを取得する（差分同期）
  - --full:   全ページを取得し、Notion 側で削除されたページを archived=true にする

環境変数:
  NOTION_TOKEN         Notion インテグレーションのシークレット（必須）
  NOTION_PAGE_IDS      表を含むページの ID または URL。カンマ区切りで複数可
  NOTION_DATABASE_IDS  同期する DB の ID または URL。カンマ区切りで複数可。
                       「ID:テーブル名」でテーブル名を指定できる（省略時は DB タイトルから生成）
                       ※ NOTION_PAGE_IDS と NOTION_DATABASE_IDS はどちらか一方だけでもよい
  DATABASE_URL         PostgreSQL 接続文字列（例: postgresql://user:pass@host:5432/db）
  PG_SCHEMA            格納先スキーマ（既定: notion）
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg
import requests
from psycopg import sql
from psycopg.types.json import Jsonb

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
PG_IDENT_MAX_BYTES = 63

# 固定カラム（Notion のプロパティ名と衝突しないよう _ 始まり）
BASE_COLUMNS = [
    ("_page_id", "text PRIMARY KEY"),
    ("_url", "text"),
    ("_created_time", "timestamptz"),
    ("_last_edited_time", "timestamptz"),
    ("_archived", "boolean NOT NULL DEFAULT false"),
    ("_properties", "jsonb"),
    ("_synced_at", "timestamptz NOT NULL DEFAULT now()"),
]

# シンプルテーブル用の固定カラム
TABLE_BASE_COLUMNS = [
    ("_row_id", "text PRIMARY KEY"),
    ("_row_index", "integer"),
    ("_last_edited_time", "timestamptz"),
    ("_archived", "boolean NOT NULL DEFAULT false"),
    ("_synced_at", "timestamptz NOT NULL DEFAULT now()"),
]

# 子要素をたどってよいブロック（トグル・カラムレイアウトなどの中にある表も探す）
CONTAINER_BLOCKS = {
    "column_list", "column", "toggle", "callout", "quote", "synced_block",
    "bulleted_list_item", "numbered_list_item", "to_do",
    "heading_1", "heading_2", "heading_3", "tab",
}

# Notion プロパティ型 → PostgreSQL 型
PG_TYPES = {
    "title": "text",
    "rich_text": "text",
    "number": "numeric",
    "select": "text",
    "status": "text",
    "multi_select": "text[]",
    "date": "timestamptz",
    "checkbox": "boolean",
    "url": "text",
    "email": "text",
    "phone_number": "text",
    "people": "text[]",
    "relation": "text[]",
    "files": "text[]",
    "created_time": "timestamptz",
    "last_edited_time": "timestamptz",
    "created_by": "text",
    "last_edited_by": "text",
    "unique_id": "text",
    "formula": "jsonb",
    "rollup": "jsonb",
}

log = logging.getLogger("notion_sync")


# ---------------------------------------------------------------- Notion API

class NotionClient:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        })

    def _request(self, method, path, body=None):
        for attempt in range(6):
            resp = self.session.request(method, f"{NOTION_API}{path}", json=body, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                log.warning("Notion API %s: %s 秒後に再試行", resp.status_code, wait)
                time.sleep(wait)
                continue
            if not resp.ok:
                raise RuntimeError(f"Notion API {resp.status_code}: {resp.text}")
            return resp.json()
        raise RuntimeError(f"Notion API が再試行後も失敗しました: {method} {path}")

    def get_database(self, database_id):
        return self._request("GET", f"/databases/{database_id}")

    def get_page(self, page_id):
        return self._request("GET", f"/pages/{page_id}")

    def get_block_children(self, block_id):
        path = f"/blocks/{block_id}/children?page_size=100"
        while True:
            data = self._request("GET", path)
            yield from data["results"]
            if not data.get("has_more"):
                return
            path = f"/blocks/{block_id}/children?page_size=100&start_cursor={data['next_cursor']}"

    def query_pages(self, database_id, edited_since=None):
        body = {"page_size": 100}
        if edited_since:
            body["filter"] = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"on_or_after": edited_since.isoformat()},
            }
        while True:
            data = self._request("POST", f"/databases/{database_id}/query", body)
            yield from data["results"]
            if not data.get("has_more"):
                return
            body["start_cursor"] = data["next_cursor"]


# ---------------------------------------------------------- 値の変換

def plain_text(rich):
    return "".join(r.get("plain_text", "") for r in rich or []) or None


def property_value(prop):
    """Notion のプロパティ値を PostgreSQL に入れる値へ変換する。"""
    t = prop["type"]
    v = prop.get(t)
    if t in ("title", "rich_text"):
        return plain_text(v)
    if t in ("select", "status"):
        return v["name"] if v else None
    if t == "multi_select":
        return [o["name"] for o in v or []]
    if t == "date":
        return v["start"] if v else None
    if t == "people":
        return [p.get("name") or p["id"] for p in v or []]
    if t == "relation":
        return [r["id"] for r in v or []]
    if t == "files":
        return [f.get("name") or (f.get(f["type"]) or {}).get("url") for f in v or []]
    if t in ("created_by", "last_edited_by"):
        return (v or {}).get("name") or (v or {}).get("id")
    if t == "unique_id":
        if not v or v.get("number") is None:
            return None
        return f"{v['prefix']}-{v['number']}" if v.get("prefix") else str(v["number"])
    if t in ("formula", "rollup"):
        return Jsonb(v)
    return v  # number, checkbox, url, email, phone_number, created_time, last_edited_time


def date_end(prop):
    v = prop.get("date")
    return v.get("end") if v else None


# ---------------------------------------------------------- 名前の整形

def truncate_ident(name, max_bytes=PG_IDENT_MAX_BYTES):
    encoded = name.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore")


def table_name_from_title(title, database_id):
    slug = re.sub(r"[^0-9a-zA-Z_぀-ヿ一-鿿]+", "_", title).strip("_").lower()
    return truncate_ident(slug or f"db_{database_id.replace('-', '')[:8]}")


def build_column_map(schema_props, base_columns=BASE_COLUMNS):
    """プロパティ名 → (カラム名, PG 型) の対応を作る。date は終了日カラムも追加。"""
    used = {c for c, _ in base_columns}
    columns = {}

    def unique(name):
        base = truncate_ident(name, PG_IDENT_MAX_BYTES - 3)
        candidate, n = truncate_ident(name), 2
        while candidate in used:
            candidate, n = f"{base}_{n}", n + 1
        used.add(candidate)
        return candidate

    for name in sorted(schema_props):
        ptype = schema_props[name]["type"]
        if ptype not in PG_TYPES:
            continue  # button など値を持たない型は raw の _properties のみに残す
        columns[name] = (unique(name), PG_TYPES[ptype])
        if ptype == "date":
            columns[f"{name}\0end"] = (unique(f"{name}_end"), "timestamptz")
    return columns


# ---------------------------------------------------------- PostgreSQL

def ensure_meta(conn, schema):
    conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    conn.execute(sql.SQL("""
        CREATE TABLE IF NOT EXISTS {}._sync_state (
            database_id   text PRIMARY KEY,
            table_name    text NOT NULL,
            last_edited   timestamptz,
            last_run_at   timestamptz,
            last_full_at  timestamptz
        )""").format(sql.Identifier(schema)))


def ensure_table(conn, schema, table, columns, base_columns=BASE_COLUMNS):
    tbl = sql.Identifier(schema, table)
    col_defs = [sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(t)) for c, t in base_columns]
    conn.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(tbl, sql.SQL(", ").join(col_defs)))
    # format_type は timestamptz を "timestamp with time zone" と返すので、比較用に同じ表記へ正規化する
    existing = dict(conn.execute(
        "SELECT attname, format_type(atttypid, atttypmod) FROM pg_attribute "
        "WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped",
        (tbl.as_string(conn),)).fetchall())
    canonical = dict(conn.execute(
        "SELECT t, format_type(t::regtype, NULL) FROM unnest(%s::text[]) AS t",
        (sorted({t for _, t in columns.values()}),)).fetchall())
    usable = {}
    for key, (col, pgtype) in columns.items():
        if col not in existing:
            log.info("  カラム追加: %s.%s (%s)", table, col, pgtype)
            conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                tbl, sql.Identifier(col), sql.SQL(pgtype)))
        elif existing[col] != canonical[pgtype]:
            log.warning("  型不一致のためスキップ: %s.%s (既存 %s / Notion %s)。値は _properties に保存されます",
                        table, col, existing[col], pgtype)
            continue
        usable[key] = (col, pgtype)
    return usable


def upsert_pages(conn, schema, table, columns, pages):
    names = [c for c, _ in BASE_COLUMNS if c != "_synced_at"] + [c for c, _ in columns.values()]
    stmt = sql.SQL(
        "INSERT INTO {tbl} ({cols}, _synced_at) VALUES ({vals}, now()) "
        "ON CONFLICT (_page_id) DO UPDATE SET {updates}, _synced_at = now()"
    ).format(
        tbl=sql.Identifier(schema, table),
        cols=sql.SQL(", ").join(map(sql.Identifier, names)),
        vals=sql.SQL(", ").join(sql.Placeholder() * len(names)),
        updates=sql.SQL(", ").join(
            sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(n)) for n in names if n != "_page_id"),
    )
    rows = []
    for page in pages:
        props = page["properties"]
        row = [page["id"], page.get("url"), page["created_time"], page["last_edited_time"],
               bool(page.get("archived") or page.get("in_trash")), Jsonb(props)]
        for key in columns:
            if key.endswith("\0end"):
                prop = props.get(key[:-4])
                row.append(date_end(prop) if prop else None)
            else:
                prop = props.get(key)
                row.append(property_value(prop) if prop else None)
        rows.append(row)
    if rows:
        with conn.cursor() as cur:
            cur.executemany(stmt, rows)
    return len(rows)


# ---------------------------------------------------------- 同期本体

def sync_database(notion, conn, schema, database_id, table_override, full):
    db = notion.get_database(database_id)
    title = plain_text(db.get("title")) or database_id
    state = conn.execute(
        sql.SQL("SELECT table_name, last_edited FROM {}._sync_state WHERE database_id = %s")
        .format(sql.Identifier(schema)), (database_id,)).fetchone()
    table = table_override or (state[0] if state else table_name_from_title(title, database_id))
    log.info("▶ %s → %s.%s (%s)", title, schema, table, "full" if full or not state else "差分")

    columns = ensure_table(conn, schema, table, build_column_map(db["properties"]))

    # 差分同期は Notion の last_edited_time が分単位で丸められるため少し巻き戻して取得する
    since = None
    if not full and state and state[1]:
        since = state[1] - timedelta(minutes=2)

    run_started = datetime.now(timezone.utc)
    seen, batch, total, max_edited = [], [], 0, state[1] if state else None
    for page in notion.query_pages(database_id, since):
        batch.append(page)
        seen.append(page["id"])
        edited = datetime.fromisoformat(page["last_edited_time"].replace("Z", "+00:00"))
        max_edited = max(max_edited, edited) if max_edited else edited
        if len(batch) >= 100:
            total += upsert_pages(conn, schema, table, columns, batch)
            batch = []
    total += upsert_pages(conn, schema, table, columns, batch)

    archived = 0
    if full or not state:
        cur = conn.execute(
            sql.SQL("UPDATE {} SET _archived = true, _synced_at = now() "
                    "WHERE NOT _archived AND NOT (_page_id = ANY(%s))").format(sql.Identifier(schema, table)),
            (seen,))
        archived = cur.rowcount

    conn.execute(sql.SQL("""
        INSERT INTO {}._sync_state (database_id, table_name, last_edited, last_run_at, last_full_at)
        VALUES (%(id)s, %(table)s, %(edited)s, %(run)s, CASE WHEN %(full)s THEN %(run)s END)
        ON CONFLICT (database_id) DO UPDATE SET
            table_name = EXCLUDED.table_name,
            last_edited = EXCLUDED.last_edited,
            last_run_at = EXCLUDED.last_run_at,
            last_full_at = COALESCE(EXCLUDED.last_full_at, {}._sync_state.last_full_at)
        """).format(sql.Identifier(schema), sql.Identifier(schema)),
        {"id": database_id, "table": table, "edited": max_edited, "run": run_started,
         "full": bool(full or not state)})
    conn.commit()
    log.info("  ✅ %d 件 upsert / %d 件 archived", total, archived)


def load_state_table(conn, schema, object_id):
    row = conn.execute(
        sql.SQL("SELECT table_name FROM {}._sync_state WHERE database_id = %s").format(sql.Identifier(schema)),
        (object_id,)).fetchone()
    return row[0] if row else None


def save_state(conn, schema, object_id, table):
    conn.execute(sql.SQL("""
        INSERT INTO {}._sync_state (database_id, table_name, last_run_at, last_full_at)
        VALUES (%s, %s, now(), now())
        ON CONFLICT (database_id) DO UPDATE SET
            table_name = EXCLUDED.table_name, last_run_at = now(), last_full_at = now()
        """).format(sql.Identifier(schema)), (object_id, table))


# ---------------------------------------------------------- ページ内の表

def find_tables(notion, block_id, context=None):
    """ページ内のブロックをたどり、インライン DB とシンプルテーブルを見つける。

    戻り値: [("database", block_id, タイトル) | ("table", block, 見出し), ...]
    シンプルテーブルには名前がないため、直前の見出しを名前の手がかりとして返す。
    """
    found, heading = [], context
    for block in notion.get_block_children(block_id):
        btype = block["type"]
        if btype in ("heading_1", "heading_2", "heading_3"):
            heading = plain_text(block[btype].get("rich_text")) or heading
        if btype == "child_database":
            found.append(("database", block["id"], block["child_database"].get("title") or None))
        elif btype == "table":
            found.append(("table", block, heading))
        elif btype in CONTAINER_BLOCKS and block.get("has_children"):
            found.extend(find_tables(notion, block["id"], heading))
    return found


def build_simple_table_columns(header_cells, width):
    """ヘッダー行のセル → {列番号: (カラム名, 型)}。空欄は col_N、重複は _2, _3… で補う。"""
    used, columns = {c for c, _ in TABLE_BASE_COLUMNS}, {}
    for i in range(width):
        text = plain_text(header_cells[i]) if header_cells and i < len(header_cells) else None
        name = (text or f"col_{i + 1}").strip()
        base, candidate, n = truncate_ident(name, PG_IDENT_MAX_BYTES - 3), truncate_ident(name), 2
        while candidate in used:
            candidate, n = f"{base}_{n}", n + 1
        used.add(candidate)
        columns[i] = (candidate, "text")
    return columns


def sync_simple_table(notion, conn, schema, block, table):
    info = block["table"]
    rows = [b for b in notion.get_block_children(block["id"]) if b["type"] == "table_row"]
    header = rows[0]["table_row"]["cells"] if info.get("has_column_header") and rows else None
    body = rows[1:] if header is not None else rows
    columns = build_simple_table_columns(header, info["table_width"])
    log.info("▶ シンプルテーブル → %s.%s (%d 列 / %d 行)", schema, table, len(columns), len(body))

    usable = ensure_table(conn, schema, table, columns, TABLE_BASE_COLUMNS)
    names = ["_row_id", "_row_index", "_last_edited_time", "_archived"] + [c for c, _ in usable.values()]
    stmt = sql.SQL(
        "INSERT INTO {tbl} ({cols}, _synced_at) VALUES ({vals}, now()) "
        "ON CONFLICT (_row_id) DO UPDATE SET {updates}, _synced_at = now()"
    ).format(
        tbl=sql.Identifier(schema, table),
        cols=sql.SQL(", ").join(map(sql.Identifier, names)),
        vals=sql.SQL(", ").join(sql.Placeholder() * len(names)),
        updates=sql.SQL(", ").join(
            sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(n)) for n in names if n != "_row_id"),
    )
    values = []
    for index, row in enumerate(body):
        cells = row["table_row"]["cells"]
        values.append([row["id"], index, row["last_edited_time"], False]
                      + [plain_text(cells[i]) if i < len(cells) else None for i in usable])
    if values:
        with conn.cursor() as cur:
            cur.executemany(stmt, values)
    cur = conn.execute(
        sql.SQL("UPDATE {} SET _archived = true, _synced_at = now() "
                "WHERE NOT _archived AND NOT (_row_id = ANY(%s))").format(sql.Identifier(schema, table)),
        ([r["id"] for r in body],))
    save_state(conn, schema, block["id"], table)
    conn.commit()
    log.info("  ✅ %d 行 upsert / %d 行 archived", len(values), cur.rowcount)


def sync_page(notion, conn, schema, page_id, full):
    """ページ内の表をすべて同期する。表ごとの失敗は数えて返す。"""
    page = notion.get_page(page_id)
    title_prop = next((p for p in page["properties"].values() if p["type"] == "title"), None)
    page_title = plain_text(title_prop["title"]) if title_prop else None
    page_title = page_title or f"page_{page_id.replace('-', '')[:8]}"
    tables = find_tables(notion, page_id)
    log.info("📄 %s: 表 %d 個を検出", page_title, len(tables))

    failed, used_names = 0, set()
    for n, (kind, obj, label) in enumerate(tables, 1):
        object_id = obj if kind == "database" else obj["id"]
        table = load_state_table(conn, schema, object_id)
        if not table:
            table = table_name_from_title(label or (page_title if len(tables) == 1 else f"{page_title}_{n}"),
                                          object_id)
            while table in used_names:
                table = truncate_ident(f"{table}_{n}")
        used_names.add(table)
        try:
            if kind == "database":
                sync_database(notion, conn, schema, object_id, table, full)
            else:
                sync_simple_table(notion, conn, schema, obj, table)
        except Exception:
            conn.rollback()
            failed += 1
            log.exception("  ❌ 同期失敗: %s (%s)", label or object_id, kind)
    return failed


def parse_id(value):
    """ID または Notion の URL から 32 桁の ID を取り出す。"""
    m = re.search(r"([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})(?:[?#/]|$)",
                  value.strip().lower())
    return m.group(1) if m else value.strip()


def parse_targets(raw):
    targets = []
    for item in filter(None, (s.strip() for s in (raw or "").split(","))):
        # URL の "https:" を区切りと誤解しないよう、最後の ":" より後ろに "/" がなければテーブル名とみなす
        head, sep, table = item.rpartition(":")
        if not sep or "/" in table or table.startswith("//"):
            head, table = item, ""
        targets.append((parse_id(head), table.strip() or None))
    return targets


def main(argv=None):
    parser = argparse.ArgumentParser(description="Notion DB を PostgreSQL に同期します")
    parser.add_argument("--full", action="store_true", help="全件取得し、削除済みページを archived にする")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    missing = [k for k in ("NOTION_TOKEN", "DATABASE_URL") if not os.environ.get(k)]
    if not (os.environ.get("NOTION_PAGE_IDS") or os.environ.get("NOTION_DATABASE_IDS")):
        missing.append("NOTION_PAGE_IDS または NOTION_DATABASE_IDS")
    if missing:
        log.error("環境変数が未設定です: %s", ", ".join(missing))
        return 2

    schema = os.environ.get("PG_SCHEMA", "notion")
    notion = NotionClient(os.environ["NOTION_TOKEN"])
    failed = 0
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        ensure_meta(conn, schema)
        conn.commit()
        for page_id, _ in parse_targets(os.environ.get("NOTION_PAGE_IDS")):
            try:
                failed += sync_page(notion, conn, schema, page_id, args.full)
            except Exception:
                conn.rollback()
                failed += 1
                log.exception("  ❌ ページの読み込み失敗: %s", page_id)
        for db_id, table in parse_targets(os.environ.get("NOTION_DATABASE_IDS")):
            try:
                sync_database(notion, conn, schema, db_id, table, args.full)
            except Exception:
                conn.rollback()
                failed += 1
                log.exception("  ❌ 同期失敗: %s", db_id)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
