# URLキーワード抽出・保存ツール

指定されたURLからコンテンツを取得し、関連キーワード情報を抽出・保存するツール及びSkillです。

## ファイル構成

```
stock_search/
├── fetch_and_save_keywords.py    # メイン実装コード
└── .claude/skills/
    └── fetch_and_save_keywords.md # Skill定義
```

## 機能

- **URL取得**: 指定されたURLからHTMLコンテンツを取得
- **キーワード抽出**: メタタグ、タイトル、本文から関連キーワードを自動抽出
- **スコアリング**: 各キーワードに重要度スコア（0-1）を付与
- **複数形式対応**: JSON、CSV、テキスト形式での出力
- **日本語対応**: 日本語形態素解析による高精度なキーワード抽出

## インストール

### 必須パッケージ

```bash
pip install requests beautifulsoup4
```

### オプション（日本語対応のため推奨）

```bash
pip install janome
```

## 使用方法

### 基本的な使い方

```bash
python fetch_and_save_keywords.py --url "https://example.com/article"
```

出力: カレントディレクトリに `keywords.json` が作成されます

### JSON形式で保存（デフォルト）

```bash
python fetch_and_save_keywords.py \
  --url "https://news.example.com/article/123" \
  --output "article_keywords.json"
```

### CSV形式で保存

```bash
python fetch_and_save_keywords.py \
  --url "https://stock.example.com/news" \
  --output "stock_keywords.csv" \
  --format csv
```

### テキスト形式で保存

```bash
python fetch_and_save_keywords.py \
  --url "https://example.com/blog" \
  --output "keywords.txt" \
  --format txt
```

### オプション一覧

| オプション | 必須 | デフォルト | 説明 |
|-----------|------|---------|------|
| `--url` | ○ | - | 取得対象のURL |
| `--output` | ✗ | `keywords.json` | 出力ファイルパス |
| `--format` | ✗ | `json` | 出力形式 (json/csv/txt) |
| `--language` | ✗ | `ja` | 言語 (ja/en) |
| `--timeout` | ✗ | `30` | タイムアウト秒数 |

## 出力例

### JSON形式
```json
{
  "url": "https://example.com/article",
  "title": "AIの最新トレンド",
  "keywords": [
    {
      "keyword": "人工知能",
      "score": 0.95,
      "source": "meta_tags,title"
    },
    {
      "keyword": "機械学習",
      "score": 0.87,
      "source": "content"
    }
  ],
  "total_keywords": 45,
  "fetched_at": "2026-04-29T12:00:00"
}
```

### CSV形式
```csv
keyword,score,source,url,fetched_date
人工知能,0.95,meta_tags,https://example.com/article,2026-04-29
機械学習,0.87,content,https://example.com/article,2026-04-29
```

### テキスト形式
```
URL: https://example.com/article
タイトル: AIの最新トレンド
取得日時: 2026-04-29T12:00:00
抽出キーワード数: 45
==================================================

1. 人工知能
   スコア: 0.95
   出典: meta_tags,title

2. 機械学習
   スコア: 0.87
   出典: content
```

## キーワード抽出アルゴリズム

### 抽出元

1. **メタタグ** (優先度: 高)
   - `<meta name="keywords">` から直接抽出
   - `<meta name="description">` から単語抽出
   - OGPタグから情報取得

2. **タイトル** (優先度: 中)
   - `<title>` タグから抽出
   - `<h1>` タグから抽出
   - 前方に出現する単語ほど重要度が高い

3. **本文コンテンツ** (優先度: 低)
   - TF（出現頻度）に基づくスコアリング
   - 最大20単語を抽出
   - 形態素解析による自然な分割

### スコアリング

各キーワードに対して 0.0～1.0 のスコアが付与されます：
- **0.9～1.0**: 極めて重要（メタタグ、タイトル由来）
- **0.7～0.9**: 重要（タイトルや説明由来）
- **0.5～0.7**: 中程度（本文由来）
- **0.1～0.5**: 低い（一度だけ出現）

## エラーハンドリング

### よくあるエラーと対処法

#### 1. URLが見つからない
```
ERROR: URL取得エラー: 404 Not Found
```
**対処**: URLが正しいか確認してください

#### 2. タイムアウト
```
ERROR: タイムアウト: https://example.com
```
**対処**: `--timeout` オプションで待機時間を増やす
```bash
python fetch_and_save_keywords.py --url "..." --timeout 60
```

#### 3. 文字化け
```
対処: 自動的にUTF-8に変換されます
```

#### 4. janomeが見つからない
```
警告: janomeがインストールされていません。
```
**対処**: 簡易版の形態素解析を使用（精度低下）
```bash
pip install janome
```

## パフォーマンス

- **単一URL**: 平均 2-5秒
- **ネットワーク待機**: 1-2秒
- **キーワード抽出**: 1-3秒
- **ファイル保存**: < 1秒

## セキュリティ上の注意

1. **robots.txt の確認**
   - スクレイピングが許可されているか確認してください

2. **User-Agent 設定**
   - ツールには適切な User-Agent が設定されています

3. **レート制限**
   - 大量URLの処理時は間隔を設けてください

## 例：複数URLの処理

```bash
#!/bin/bash

urls=(
  "https://example.com/article1"
  "https://example.com/article2"
  "https://example.com/article3"
)

for url in "${urls[@]}"; do
  echo "処理中: $url"
  python fetch_and_save_keywords.py --url "$url" --output "keywords_$(date +%s).json"
  sleep 2  # レート制限
done
```

## トラブルシューティング

### キーワード数が少ない
- メタタグが設定されていないサイトの場合、本文のみから抽出
- 英語サイトの場合は `--language en` を試す

### スコアが低い
- 検出されたキーワードが本文に出現しない場合、本文由来になる
- タイトルにキーワードがない場合、スコアが低くなる

### メモリ不足
- 大規模なHTMLページの場合、メモリを増やす
- 複数並行実行は避ける

## ライセンス

MIT License

## 貢献

改善提案やバグ報告は issue でお願いします。

## 参考資料

- [BeautifulSoup ドキュメント](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Requests ドキュメント](https://docs.python-requests.org/)
- [Janome ドキュメント](https://mocobeta.github.io/janome/)
