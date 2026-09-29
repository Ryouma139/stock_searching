---
name: notion_save
description: Save stock report markdown files from stock_save/ to Notion workspace under Claude Contents/stock_reports via Notion MCP. Trigger when user runs /notion_save <企業名 or ファイルパス>, or says "Notionに保存して", "Notionにアップして", "ノーションに保存して".
---

# notion_save

`stock_save/` フォルダの株情報レポート（Markdown）を Notion MCP で `Claude Contents/stock_reports` 配下に保存します。

## 使い方

```sh
/notion_save <企業名 or ファイルパス>
```

例：

```sh
# 企業名で指定（最新ファイルを対象）
/notion_save 安川電機

# ファイルパスで直接指定
/notion_save stock_save/安川電機_20260504.md

# stock_save/ フォルダ全体を一括保存
/notion_save stock_save/
```

## 手順

1. 対象ファイルパス（または企業名）を受け取る

   ```js
   console.log(`[1/4] 📂 対象: ${target}`)
   ```

   - 企業名が指定された場合 → `stock_save/` から `{企業名}_*.md` に一致する最新ファイルを自動検索する
   - フォルダパスが指定された場合 → 配下の `.md` ファイルを全て対象とする

2. ファイルの存在を確認する

   ```js
   console.log(`[2/4] 🔎 ファイル確認中...`)
   ```

   - **存在する** → 手順 3 へ進む
   - **存在しない** → エラーをユーザーに通知して処理を中断する

   ```js
   // 存在する場合
   console.log(`[2/4] ✅ ${files.length} 件のファイルを確認`)
   // 存在しない場合
   console.log(`[2/4] ❌ ファイルが見つかりません: ${target}`)
   console.log(`  → stock-searching スキルでレポートを先に生成してください`)
   ```

3. Notion MCP で階層ページを確認・作成する

   ```js
   console.log(`[3/5] 📓 Notion MCP 接続中...`)
   ```

   > **重要**: 手順 3a → 3b → 3c → 3d を必ず順番に実行すること。3b の日付フォルダ作成をスキップしてはならない。

   - **3a. `Claude Contents/stock_reports` を確認・作成する**
     - `notion-search` で `stock_reports` を検索する
     - 存在しない場合は `notion-create-pages` で作成する（親: `Claude Contents`）
     - 取得した `stock_reports` ページの ID を変数 `stockReportsPageId` に保存する

   ```js
   console.log(`  [3a] stock_reports ページID: ${stockReportsPageId}`)
   ```

   - **3b. 日付フォルダページ `YYYYMMDD` を確認・作成する（必須ステップ）**
     - ファイル名 `YYYYMMDD_企業名.md` の先頭 8 文字から日付 `YYYYMMDD` を取得する
     - `notion-search` で `stock_reports` 配下に `YYYYMMDD` という名前のページが存在するか確認する
     - 存在しない場合は `notion-create-pages` で作成する（**親: `stockReportsPageId`**）
     - 同じ日付のファイルが複数ある場合は同じ日付フォルダページを使い回す
     - 取得した日付フォルダの ID を変数 `dateFolderPageId` に保存する

   ```js
   console.log(`  [3b] 日付フォルダ作成/確認: stock_reports/${date}  ID: ${dateFolderPageId}`)
   ```

   - **3c. 日付フォルダ配下に企業ページを作成する**
     - `notion-create-pages` で子ページを作成する（**親: `dateFolderPageId`**）
     - ページ名は `YYYYMMDD_企業名` 形式とする

     ページ階層の形式：
     ```text
     Claude Contents/stock_reports/YYYYMMDD/YYYYMMDD_企業名
     ```

     例：
     ```text
     Claude Contents/stock_reports/20260929/20260929_メドレックス
     ```

   ```js
   files.forEach(f => console.log(`  [3c] ${f.path} → stock_reports/${f.date}/${f.date}_${f.company}`))
   ```

   - **3d. Markdown の内容を Notion ページに書き込む**

     | MD セクション | Notion ブロック |
     |---|---|
     | `## 基本情報` | テーブル or callout |
     | `## 企業概要` | paragraph |
     | `## 株価情報` | bulleted list |
     | `## 最新ニュース` | numbered list |
     | `## 主要事業 × 業界キーワード` | heading2 + bulleted list |
     | キーワード（バッククォート） | inline code |
     | 出典リンク | bookmark ブロック |

4. ページ作成が完了したら `notion-search` で実際に存在するか検索して確認する

   ```js
   console.log(`[4/5] 🔎 作成確認中...`)
   // notion-search で YYYYMMDD_企業名 を検索し、stock_reports/YYYYMMDD/ 配下に存在することを確認
   ```

5. 保存完了をユーザーに通知する

   ```js
   console.log(`[5/5] ✅ Notion 保存完了 (${savedCount} 件)`)
   savedFiles.forEach(f => console.log(`  → Claude Contents/stock_reports/${f.date}/${f.date}_${f.company}`))
   ```

## 注意

- Notion MCP（`settings.json` の `mcpServers.notion`）の接続と OAuth 認証が必要
- 未認証の場合は `/mcp` → `notion` → `Authenticate` で認証してから再実行する
- 日付フォルダページ配下に同名の企業ページが既に存在する場合はユーザーに確認の上、上書きまたはスキップを選択させる
- `stock_save/` フォルダが存在しない場合は `stock-searching` スキルを先に実行するようユーザーに案内する
- **日付フォルダ（3b）を作成せずに企業ページ（3c）を直接 `stock_reports` 配下に作成してはならない**
