-- Cloudflare D1 (SQLite) スキーマ
-- 適用: npx wrangler d1 execute stock-sim --remote --file=db/schema.sql

-- 銘柄マスタ
CREATE TABLE IF NOT EXISTS tickers (
  ticker     TEXT PRIMARY KEY,          -- 例: 7203.T
  name       TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- 月次終値（検索・集計したい場合のみ。表示だけなら R2/静的 JSON で十分）
CREATE TABLE IF NOT EXISTS monthly_prices (
  ticker TEXT NOT NULL REFERENCES tickers(ticker),
  ym     TEXT NOT NULL,                 -- YYYY-MM
  close  REAL NOT NULL,
  PRIMARY KEY (ticker, ym)
);

-- ユーザーが保存したシミュレーション条件
CREATE TABLE IF NOT EXISTS scenarios (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT NOT NULL,
  mode        TEXT NOT NULL CHECK (mode IN ('fixed', 'historical')),
  ticker      TEXT,
  annual_rate REAL NOT NULL DEFAULT 0.10,  -- 想定年率 10%
  initial     INTEGER NOT NULL DEFAULT 0,
  monthly     INTEGER NOT NULL,
  years       INTEGER NOT NULL,
  final_value REAL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_scenarios_created ON scenarios(created_at DESC);
