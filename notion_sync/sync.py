"""Notion データベース → PostgreSQL 同期スクリプト。

Notion のデータベースごとに PostgreSQL のテーブルを 1 つ用意し、ページ（行）を
page_id をキーに UPSERT する。テーブルとカラムは Notion のプロパティ定義から
自動で作成・追加される。

  - 通常実行: 前回同期以降に更新されたページだけを取得する（差分同期）
  - --full:   全ページを取得し、Notion 側で削除されたページを archived=true にする

環境変数:
  NOTION_TOKEN         Notion インテグレーションのシークレット（必須）
  NOTION_DATABASE_IDS  同期する DB の ID。カンマ区切りで複数可。
                       「ID:テーブル名」でテーブル名を指定できる（省略時は DB タイトルから生成）
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


def build_column_map(schema_props):
    """プロパティ名 → (カラム名, PG 型) の対応を作る。date は終了日カラムも追加。"""
    used = {c for c, _ in BASE_COLUMNS}
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


def ensure_table(conn, schema, table, columns):
    tbl = sql.Identifier(schema, table)
    col_defs = [sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(t)) for c, t in BASE_COLUMNS]
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


def parse_targets(raw):
    targets = []
    for item in filter(None, (s.strip() for s in raw.split(","))):
        db_id, _, table = item.partition(":")
        targets.append((db_id.strip(), table.strip() or None))
    return targets


def main(argv=None):
    parser = argparse.ArgumentParser(description="Notion DB を PostgreSQL に同期します")
    parser.add_argument("--full", action="store_true", help="全件取得し、削除済みページを archived にする")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    missing = [k for k in ("NOTION_TOKEN", "NOTION_DATABASE_IDS", "DATABASE_URL") if not os.environ.get(k)]
    if missing:
        log.error("環境変数が未設定です: %s", ", ".join(missing))
        return 2

    schema = os.environ.get("PG_SCHEMA", "notion")
    notion = NotionClient(os.environ["NOTION_TOKEN"])
    failed = 0
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        ensure_meta(conn, schema)
        conn.commit()
        for db_id, table in parse_targets(os.environ["NOTION_DATABASE_IDS"]):
            try:
                sync_database(notion, conn, schema, db_id, table, args.full)
            except Exception:
                conn.rollback()
                failed += 1
                log.exception("  ❌ 同期失敗: %s", db_id)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
