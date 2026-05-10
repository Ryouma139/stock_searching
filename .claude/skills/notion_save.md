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

3. Notion MCP で `/stock_reports/` ページを確認・作成する

   ```js
   console.log(`[3/4] 📓 Notion MCP 接続中...`)
   ```

   - 3a. `Claude Contents/stock_reports` ページが存在するか `notion-search` で確認する
     - 存在しない場合は `notion-create-pages` で自動作成する（親: `Claude Contents`）

   ```js
   console.log(`  [NOTION] Claude Contents/stock_reports ページを確認`)
   ```

   - 3b. 各ファイルについて `Claude Contents/stock_reports` 配下に子ページを作成する

     ページ名の形式：
     ```text
     Claude Contents/stock_reports/YYYYMMDD_(企業名)
     ```

     例：
     ```text
     Claude Contents/stock_reports/20260504_安川電機
     ```

   - 3c. Markdown の内容を以下のセクション構成で Notion ページに書き込む

     | MD セクション | Notion ブロック |
     |---|---|
     | `## 基本情報` | テーブル or callout |
     | `## 企業概要` | paragraph |
     | `## 株価情報` | bulleted list |
     | `## 最新ニュース` | numbered list |
     | `## 主要事業 × 業界キーワード` | heading2 + bulleted list |
     | キーワード（バッククォート） | inline code |
     | 出典リンク | bookmark ブロック |

   ```js
   files.forEach(f => console.log(`  [NOTION] ${f} → Claude Contents/stock_reports/`))
   ```

4. 保存完了をユーザーに通知する

   ```js
   console.log(`[4/4] ✅ Notion 保存完了 (${savedCount} 件)`)
   savedFiles.forEach(f => console.log(`  → Claude Contents/stock_reports/${f}`))
   ```

## 注意

- Notion MCP（`settings.json` の `mcpServers.notion`）の接続と OAuth 認証が必要
- 未認証の場合は `/mcp` → `notion` → `Authenticate` で認証してから再実行する
- 同名ページが既に存在する場合はユーザーに確認の上、上書きまたはスキップを選択させる
- `stock_save/` フォルダが存在しない場合は `stock-searching` スキルを先に実行するようユーザーに案内する
