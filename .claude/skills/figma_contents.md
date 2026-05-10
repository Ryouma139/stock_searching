---
name: figma_contents
description: Read a stock report markdown from stock_save/, create a Figma design card via MCP, export as PNG and save to figma_contents/. Trigger when user says "Figmaで図式化して", "Figmaに出力して", "株レポートを画像にして", "ビジュアライズして".
---

# figma_contents

`stock_save/` の株情報レポート（Markdown）を解析し、Figma MCP でデザインカードを生成・PNG としてエクスポートして保存します。

## 使い方

```sh
/figma_contents <企業名 or ファイルパス>
```

例：

```sh
# 企業名で指定（最新ファイルを対象）
/figma_contents 安川電機

# ファイルパスで直接指定
/figma_contents stock_save/安川電機_20260504.md
```

## 手順

1. 対象ファイルパス（または企業名）を受け取る

   ```js
   console.log(`[1/6] 📂 対象: ${target}`)
   ```

   - 企業名が指定された場合 → `stock_save/` から `{企業名}_*.md` に一致する最新ファイルを自動検索する

2. ファイルの存在を確認する

   ```js
   console.log(`[2/6] 🔎 ファイル存在確認中...`)
   // 存在する場合
   console.log(`[2/6] ✅ ファイル確認OK: ${filePath}`)
   // 存在しない場合
   console.log(`[2/6] ❌ ファイルが見つかりません: ${target}`)
   console.log(`  → stock-searching スキルでレポートを先に生成してください`)
   ```

3. ファイルの内容を読み込み、以下を抽出する

   ```js
   console.log(`[3/6] 🔍 構造解析中...`)
   ```

   抽出するセクション：

   | MD セクション | 抽出内容 |
   |---|---|
   | `## 基本情報` | 企業名・ティッカー・業界・設立・代表者 |
   | `## 株価情報` | 現在値・52週レンジ・時価総額・PER/PBR |
   | `## 最新ニュース` | ニュース見出し（最大5件） |
   | `## 主要事業 × 業界キーワード` | キーワード一覧・各キーワードのトレンド要約 |

4. Figma MCP を使いデザインカードを生成する

   ```js
   console.log(`[4/6] 🎨 Figma MCP でデザイン生成中...`)
   ```

   レイアウト構成（Auto Layout / Vertical）：

   ```
   ┌─────────────────────────────────────┐
   │  [企業名]  [ティッカー]  [業界]       ← ヘッダー（背景: #1A2B5E）
   ├──────────────┬──────────────────────┤
   │ 基本情報     │ 株価情報              ← 2カラム（背景: #F5F7FF）
   │ 設立 / 代表  │ 現在値 / 52週レンジ  │
   │              │ 時価総額 / PER / PBR │
   ├──────────────┴──────────────────────┤
   │ 最新ニュース（箇条書き）              ← セクション（背景: #FFFFFF）
   ├─────────────────────────────────────┤
   │ 業界キーワード                        ← バッジ群（横並び Wrap）
   │ [キーワード1] [キーワード2] ...       │
   ├─────────────────────────────────────┤
   │ キーワード別 業界トレンド             ← 各キーワードのサマリー
   │  ・キーワード1: トレンド説明          │
   │  ・キーワード2: トレンド説明          │
   └─────────────────────────────────────┘
   ```

   スタイル仕様：

   | 要素 | フォント | サイズ | カラー |
   |---|---|---|---|
   | 企業名（H1） | Bold | 20px | #FFFFFF |
   | ティッカーバッジ | Semi Bold | 12px | #3D5AFE |
   | セクション見出し | Semi Bold | 14px | #1A2B5E |
   | 本文テキスト | Regular | 12px | #2D2D2D |
   | 株価（現在値） | Bold | 18px | #1B8C4E |
   | キーワードバッジ | Regular | 11px | bg:#E8F0FE, text:#1A2B5E |

5. Figma MCP でデザインを PNG としてエクスポートする

   ```js
   console.log(`[5/6] 📤 画像エクスポート中... (形式: PNG, 解像度: 2x)`)
   ```

   - 形式：PNG（デフォルト）または SVG
   - 解像度：2x（高解像度）

6. `{workspace}/figma_contents/` に画像を保存する

   ```text
   {workspace}/figma_contents/YYYY/MM/DD_(企業名).png
   ```

   例：

   ```text
   figma_contents/2026/05/04_安川電機.png
   ```

   ```js
   console.log(`[6/6] ✅ 画像保存完了: ${outputPath}`)
   ```

## 注意

- Figma MCP（`settings.json` の `mcpServers.figma`）が起動していることが前提
- MCP が未接続の場合はエラーをユーザーに通知して処理を中断する
- エクスポート形式はユーザーが PNG / SVG を選択可能（未指定時は PNG）
- 元の `.md` ファイルは変更しない
- `figma_contents/YYYY/MM/` ディレクトリが存在しない場合は自動作成する
- 複数企業を一括処理する場合は企業ごとに個別フレームを作成し、1企業1ファイルで保存する
