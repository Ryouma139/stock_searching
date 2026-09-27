---
name: stock_db
description: Read stock report pages from Notion (Claude Contens/stock_reports/YYYYMMDD/YYYYMMDD_{企業名}) via Notion MCP, extract the 終値/前日比/前日終値/急騰日 table, and append a row to the Notion database Claude Contens/株価DB (or to Claude Contens/参照DB when the same 銘柄 already exists in 株価DB). Trigger when user runs /stock_db <YYYYMMDD or 企業名>, or says "株価DBに追記して", "株価DBに登録して", "DBに追加して".
---

# stock_db

Notion の `Claude Contens/stock_reports/YYYYMMDD/YYYYMMDD_{企業名}` ページから株価テーブルを読み取り、`Claude Contens/株価DB` に 1 銘柄 1 行で追記します。
株価DB に同じ銘柄がすでに存在する場合は、株価DB ではなく `Claude Contens/参照DB` に追記します。

## 使い方

```sh
/stock_db <YYYYMMDD | 企業名 | YYYYMMDD 企業名>
```

例：

```sh
# 日付フォルダ配下の全企業ページを対象
/stock_db 20260925

# 企業名で指定（最新日付のページを対象）
/stock_db THE_WHY_HOW_DO_COMPANY

# 日付＋企業名で1ページだけ対象
/stock_db 20260925 THE_WHY_HOW_DO_COMPANY
```

引数なしの場合は、JST の今日の日付を `YYYYMMDD` として扱います。

## 対象 Notion リソース

| 種別 | 名前 | ID / URL |
|---|---|---|
| 親ページ | Claude Contens | `3502e8c9228c80b8b30dd00ff67f0f13` |
| レポート格納ページ | Claude Contens/stock_reports | `3562e8c9228c8131be94deec59b4f022` |
| 追記先 DB | Claude Contens/株価DB | `1e4e439baae24f2698fbf4b46f9fbe18` |
| 追記先データソース | 株価DB | `collection://c01b1aab-9648-4c46-bd78-f98e28667d61` |
| 追記先 DB（銘柄重複時） | Claude Contens/参照DB | `c86df9f909a64bc083110cb10e5175f6` |
| 追記先データソース（銘柄重複時） | 参照DB | `collection://3e12b459-2387-40f7-bc20-0353e38958c6` |

> ワークスペース上のページ名は `Claude Contens`（`Contents` ではない）。ID が変わっていた場合は `notion-search` で `株価DB` / `参照DB` / `stock_reports` を検索し直す。

## 株価DB / 参照DB スキーマ

両 DB は同じ構造（参照DB には `参照回数` が無い）。

| プロパティ | 型 | 書式 | 書き込む値の例 |
|---|---|---|---|
| `銘柄` | title | - | `THE_WHY_HOW_DO_COMPANY` |
| `終値（推定）` | number | 円 | `170` |
| `前日比` | number | 円 | `37`（下落時は `-37`） |
| `前日比率` | number | % | `0.2794`（**小数で保存**。27.94% → 0.2794） |
| `前日終値（推定）` | number | 円 | `133` |
| `急騰日` | date | YYYY/MM/DD | `date:急騰日:start` = `2026-09-25`, `date:急騰日:is_datetime` = `0` |
| `参照回数` | number | - | 株価DB のみ。新規追加時は空。同じ銘柄を参照DB に追記するたびに +1 |

## 手順

1. 対象ページを特定する

   ```js
   console.log(`[1/5] 📂 対象: ${target}`)
   ```

   - `YYYYMMDD` 指定 → `stock_reports` 配下の `YYYYMMDD` ページを `notion-fetch` し、子ページのうちタイトルが `YYYYMMDD_*` のものを全て対象とする
     - 日付フォルダ直下にあるサマリーページ（タイトルが `YYYYMMDD` のみのもの）は対象外
   - 企業名指定 → `notion-search`（`page_url` に `stock_reports` を指定）で `_{企業名}` を検索し、タイトルが `YYYYMMDD_{企業名}` に一致する最新日付のページを対象とする
   - 日付＋企業名指定 → `YYYYMMDD_{企業名}` に完全一致する 1 ページを対象とする
   - 該当ページが 0 件 → ユーザーに通知して中断する

   ```js
   console.log(`[1/5] ✅ ${pages.length} 件のレポートページを検出`)
   // 0件の場合
   console.log(`[1/5] ❌ Claude Contens/stock_reports/${date} にレポートページがありません`)
   ```

2. 各ページを `notion-fetch` し、株価テーブルを抽出する

   ```js
   console.log(`[2/5] 🔎 株価テーブル抽出中...`)
   ```

   - ページ本文の `<table>`（通常は `## 株価情報` → `### 現在値`）から、1 列目が以下のラベルの行を読み取る

     | テーブルの行ラベル | 例 | 対応する DB プロパティ |
     |---|---|---|
     | `終値` / `終値（推定）` / `現在値` | `¥170（推定）` | `終値（推定）` |
     | `前日比` | `+¥37（+27.94%）` | `前日比` / `前日比率` |
     | `前日終値` / `前日終値（推定）` | `¥133（推定）` | `前日終値（推定）` |
     | `急騰日` | `2026-09-25 JST` | `急騰日` |

   - **テーブルが無い、または `終値`・`前日比`・`前日終値` のいずれかが欠けている場合は、そのページをスキップ**し、理由を記録する（推測で値を埋めない）
   - `急騰日` 行が無い場合は `取得日時` 行の日付を使い、それも無ければページタイトルの `YYYYMMDD` を使う（どれを使ったかを完了報告に含める）

3. 値を数値に変換する

   | 元の文字列 | 変換ルール | 結果 |
   |---|---|---|
   | `¥170（推定）` | `¥`・`円`・`,`・`（推定）`・`約` を除去して数値化 | `170` |
   | `+¥37（+27.94%）` | 括弧の外 → 前日比（符号を保持）、括弧内の `%` → 100 で割る | `37` / `0.2794` |
   | `-¥12（-5.10%）` | マイナス（`-` / `−` / `▲`）は負の値にする | `-12` / `-0.051` |
   | `¥133（推定）` | 終値と同じ | `133` |
   | `2026-09-25 JST` | `YYYY-MM-DD` 部分のみ取り出す（`2026/09/25` や `2026年9月25日` も同様） | `2026-09-25` |

   - 前日比率が表に無い場合は `前日比 / 前日終値` を小数第 4 位で丸めて算出する
   - 数値に変換できない値（`-`、`未公開` など）があればそのページはスキップする
   - `銘柄` にはページタイトルから `YYYYMMDD_` を除いた企業名を入れる

4. 株価DB に同じ銘柄があるかで追記先を振り分ける

   ```js
   console.log(`[4/5] 📓 追記先を判定中...`)
   ```

   - 4a. `notion-query-data-sources`（SQL モード）で、株価DB に同じ `銘柄` の行があるか確認する（急騰日は問わない）

     ```sql
     SELECT url, "date:急騰日:start", "参照回数" FROM "collection://c01b1aab-9648-4c46-bd78-f98e28667d61"
     WHERE "銘柄" = ?
     ORDER BY "date:急騰日:start" ASC
     ```

   - 4b. 判定結果に応じて追記先を決める

     | 株価DB の状態 | 追記先 |
     |---|---|
     | 同じ `銘柄` の行が無い | **株価DB** に追記 |
     | 同じ `銘柄` の行がある | 株価DB の `参照回数` を +1 した**後に**、**参照DB** に追記（株価DB に行は追加しない） |
     | 株価DB または参照DB に同じ `銘柄` かつ同じ `急騰日` の行がすでにある | 追記せずスキップ（同じレポートを再実行したケース）。`参照回数` もカウントしない |

     - 参照DB 側の重複確認は次の SQL で行う

       ```sql
       SELECT url FROM "collection://3e12b459-2387-40f7-bc20-0353e38958c6"
       WHERE "銘柄" = ? AND "date:急騰日:start" = ?
       ```

     - 1 回の実行で同じ銘柄のページが複数ある場合は `急騰日` の古い順に 1 件ずつ処理し、先に株価DB へ追記した銘柄は「株価DB に存在する」ものとして扱う（2 件目以降は参照回数 +1 → 参照DB へ）。このため株価DB への追加は `allow_async: false` で行い、作成された行の URL を控えておく
     - 既存行の上書きはユーザーが明示的に求めた場合のみ `notion-update-page` で行う

   - 4c. 参照DB に追記する銘柄は、先に株価DB の `参照回数` をカウントアップする

     - 4a の結果の行（同じ銘柄が株価DB に複数ある場合は `急騰日` が最も古い行）を対象にする
     - 新しい値 = 現在の `参照回数` + 1（空の場合は `0` とみなし `1` にする）
     - `notion-update-page` の `update_properties` で書き込む

       ```json
       {
         "page_id": "<4a で取得した株価DB 行の url>",
         "command": "update_properties",
         "properties": { "参照回数": 1 },
         "allow_async": false
       }
       ```

     - 同じ実行内で同じ銘柄を複数回カウントする場合は、直前に書き込んだ値に +1 する（4a の古い値を使い回さない）
     - カウントアップに失敗した場合はその銘柄の参照DB への追記も行わず、失敗として報告する

     ```js
     console.log(`  [株価DB] ${name} 参照回数 ${before ?? 0} → ${after}`)
     ```

   - 4d. 追記先ごとに `notion-create-pages` でまとめて追加する（1 回の呼び出しで複数行可）。プロパティは両 DB 共通

     ```json
     {
       "parent": { "type": "data_source_id", "data_source_id": "<株価DB または 参照DB の data_source_id>" },
       "pages": [
         {
           "properties": {
             "銘柄": "THE_WHY_HOW_DO_COMPANY",
             "終値（推定）": 170,
             "前日比": 37,
             "前日比率": 0.2794,
             "前日終値（推定）": 133,
             "date:急騰日:start": "2026-09-25",
             "date:急騰日:is_datetime": 0
           }
         }
       ]
     }
     ```

     - 株価DB: `c01b1aab-9648-4c46-bd78-f98e28667d61`
     - 参照DB: `3e12b459-2387-40f7-bc20-0353e38958c6`

   ```js
   rows.forEach(r => console.log(`  [${r.dest}] ${r.銘柄} 終値¥${r.終値} 前日比${r.前日比}(${r.前日比率}) 急騰日${r.急騰日}`))
   ```

5. 結果をユーザーに通知する

   ```js
   console.log(`[5/5] ✅ 追記完了: 株価DB ${addedMain} 件 / 参照DB ${addedRef} 件（参照回数カウント ${counted} 件）/ 重複スキップ ${dup} 件 / テーブルなしスキップ ${skipped} 件`)
   skippedPages.forEach(p => console.log(`  ⏭ ${p.title}: ${p.reason}`))
   ```

## 注意

- Notion MCP の接続と OAuth 認証が必要。未認証の場合は `/mcp` → `notion` → `Authenticate` で認証してから再実行する
- `前日比率` は Notion 側がパーセント表示のため、必ず小数（27.94% → `0.2794`）で書き込む。`27.94` を入れると 2794% と表示される
- `参照回数` は株価DB に同じ銘柄が既にあり、参照DB へ追記するときだけ +1 する（新規追加時は空のまま）
- レポートページが無い場合は、先に `stock_searching` → `notion_save` スキルを実行するようユーザーに案内する
