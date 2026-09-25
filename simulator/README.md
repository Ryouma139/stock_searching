# 積立・リターン シミュレーター（雛形）

銘柄の株価データを使い、毎月の積立投資をシミュレーションします。

- **想定年率モード**：一定の年率（初期値 **10%**）で毎月複利運用した場合
- **過去株価モード**：実際の月末終値で毎月同じ金額を買い付けた場合（ドルコスト平均法）

計算は **ブラウザ内の Python（Pyodide）** で行います。そのため Cloudflare Pages の静的ホスティングだけで動きます。

## 構成

```
simulator/
├─ public/                 ← Cloudflare Pages にデプロイ
│  ├─ index.html           画面（Chart.js でグラフ・表を描画）
│  ├─ sim.py               シミュレーションロジック（Python / 標準ライブラリのみ）
│  └─ data/
│     ├─ index.json        銘柄一覧
│     └─ SAMPLE.json       動作確認用の架空データ（実績年率 10%）
├─ scripts/fetch_prices.py yfinance で月次終値を取得 → public/data/*.json
├─ db/schema.sql           D1 スキーマ（シナリオ保存など、必要になったら）
└─ worker/                 D1 を読み書きする Python Worker API（任意）
```

## ローカルで動かす

```bash
cd simulator/public
python -m http.server 8000     # http://localhost:8000
python sim.py                  # ロジック単体の確認
```

## 株価データを追加する

```bash
cd simulator
pip install -r requirements.txt
python scripts/fetch_prices.py 7203.T 6758.T ^N225 --years 20
```

## デプロイ（Cloudflare Pages）

```bash
npx wrangler pages deploy simulator/public --project-name=stock-simulator
```

`.github/workflows/simulator-deploy.yml` を使うと、株価の取得からデプロイまでを自動化できます。
リポジトリに `CLOUDFLARE_API_TOKEN` と `CLOUDFLARE_ACCOUNT_ID` をシークレットとして登録し、手動で実行するか `schedule` を有効にしてください。

## DB の選び方

| 用途 | 推奨 | 理由 |
|---|---|---|
| 株価の時系列（表示用） | **静的 JSON**（大きくなったら **R2**） | 読み取り専用で、まとめて取得するだけなので DB は不要。CDN から高速に配信できる |
| シナリオ保存・ユーザーデータ・銘柄の検索や集計 | **D1**（SQLite） | SQL が使え、Workers から直接読み書きできる。無料枠が大きい |
| API レスポンスのキャッシュ・設定値 | **KV** | キーと値で読むだけの用途に向く。結果整合性なので書き込みの多い用途には不向き |

**まずは DB なし（静的 JSON）で始め、保存機能が必要になった時点で D1 を追加する**のがおすすめです。

D1 を追加する手順：

```bash
cd simulator/worker
npx wrangler d1 create stock-sim            # 表示された database_id を wrangler.toml に記入
npx wrangler d1 execute stock-sim --remote --file=../db/schema.sql
npx wrangler deploy
```

> Python Workers は機能追加が続いているため、API の書き方は公式ドキュメントで最新版を確認してください。
