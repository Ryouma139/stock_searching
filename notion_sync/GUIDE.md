# Notion → PostgreSQL 同期 設計メモ

Notion ページ内の表（株価・銘柄情報）を PostgreSQL に移行し、定期的に自動同期する仕組みについて、検討した内容をまとめたものです。
設定手順の詳細は [README.md](README.md) を参照してください。

## 全体構成

```
Notion（ページ内の表）
   │  Notion API（NOTION_TOKEN）
   ▼
GitHub Actions で notion_sync/sync.py を実行   ← 決まった時刻に GitHub のサーバーが自動実行
   │  SQL（DATABASE_URL）
   ▼
クラウド PostgreSQL（Supabase / Neon など）
```

| ファイル | 役割 |
|---|---|
| `.github/workflows/notion_sync.yml` | 定期実行の設定（いつ・何を実行するか） |
| `notion_sync/sync.py` | 同期処理の本体 |
| `notion_sync/requirements.txt` | 必要な Python ライブラリ |
| `notion_sync/tests/test_sync.py` | テスト |

---

## 1. クラウド DB を使用したい理由と、使用しなかった場合

### 理由

GitHub Actions は **GitHub のクラウド上のサーバー** で実行されます。そのサーバーから接続できる場所に DB がなければ、同期先がありません。

```
GitHub のサーバー ──(インターネット)──▶ クラウド DB        ✅ 接続できる
GitHub のサーバー ──(インターネット)──▶ 自宅 PC の DB      ❌ 接続できない
```

- **PC を閉じていても動く**：実行も DB もクラウドにあるので、PC の電源状態に関係なく同期されます
- **どこからでも見られる**：スマホや別の PC、将来作る Web サイトからも同じデータを参照できます
- **管理の手間が少ない**：バックアップ・更新・障害対応はサービス側が行います

### クラウド DB を使わなかった場合（自分の PC の PostgreSQL / Docker）

| 問題 | 内容 |
|---|---|
| GitHub Actions から接続できない | 自宅 PC はルーターの内側にあり外部から見えない。`localhost` と書いても GitHub のサーバー自身を指してしまう |
| PC を閉じると止まる | DB（Docker 含む）が停止し、同期先がなくなる |
| データの保全 | PC の故障 = データの消失。バックアップは自分で行う必要がある |

> **Docker で動かしている = クラウド ではありません。** Docker は「入れ物」で、置き場所が自分の PC ならローカルです。

### それでもローカルで使いたい場合

GitHub Actions は使わず、**PC 上で定期実行**します（Windows タスクスケジューラ / Mac・Linux の cron）。

```sh
# 例：PC 上の cron（毎日 8:00）
0 8 * * * cd /path/to/stock_searching && DATABASE_URL=postgresql://user:pass@localhost:5432/db python notion_sync/sync.py --full
```

- PC が起動しているときだけ実行されます
- 閉じていた間の変更は、次回起動時の同期でまとめて反映されます

### 主なクラウド PostgreSQL

| サービス | 特徴 | 向いている人 |
|---|---|---|
| **Supabase** | 無料枠あり。管理画面で表を閲覧・編集できる。東京リージョンあり。一定期間アクセスがないと一時停止（毎日同期していれば止まらない） | 使いやすさ重視 |
| **Neon** | 無料枠あり。未使用時は自動停止し使った分だけ課金。Cloudflare との連携例が多い | コスト最小・Cloudflare 併用 |
| Render / Railway / Aiven | アプリのホスティングと一緒に使いやすい | ― |
| AWS RDS・Aurora / Google Cloud SQL / Azure | 本格運用向け。基本的に常時課金 | 仕事・チーム利用 |

※ 料金・無料枠は変更されることがあるため、契約前に公式サイトで確認してください。

---

## 2. 必要な設定（トークンなど）

### 2-1. Notion 側

1. **インテグレーションを作成**
   <https://www.notion.so/profile/integrations> →「新しいインテグレーション」→ 作成後に表示される **シークレット**（`ntn_...` / `secret_...`）を控える
2. **対象ページにインテグレーションを接続**
   ページ右上「…」→「接続」→ 作成したインテグレーションを選択
   - 接続しないと、トークンがあっても `object_not_found`（404）になり読めません
   - 親ページで接続すれば子ページ・ページ内の表にも適用されます
   - ページを Web 公開する必要は **ありません**
3. **ページの URL をコピー**
   ページ右上「…」→「リンクをコピー」

> Claude で使っている Notion 連携（MCP）のログインは GitHub Actions では使えません。必ずインテグレーションを別に作成します。

### 2-2. クラウド DB 側

- Supabase / Neon などで DB を作成し、**接続文字列** を控える
  例：`postgresql://user:password@host:5432/dbname`
- IP アドレス制限を設定している場合は、外部からの接続を許可する（GitHub のサーバーの IP は毎回変わるため）

### 2-3. GitHub 側

**Settings → Secrets and variables → Actions** に登録します。

| 種類 | 名前 | 値 | 必須 |
|---|---|---|---|
| Secret | `NOTION_TOKEN` | Notion インテグレーションのシークレット | ✅ |
| Secret | `DATABASE_URL` | クラウド PostgreSQL の接続文字列 | ✅ |
| Variable | `NOTION_PAGE_IDS` | 表を含むページの URL（複数はカンマ区切り） | ✅ ※1 |
| Variable | `NOTION_DATABASE_IDS` | DB を直接指定する場合の URL。`URL:テーブル名` で名前指定可 | ※1 |
| Variable | `PG_SCHEMA` | 格納先スキーマ（既定 `notion`） | 任意 |

※1 `NOTION_PAGE_IDS` と `NOTION_DATABASE_IDS` はどちらか一方があれば動きます。

- **Secret** は暗号化され、登録後は誰も中身を見られません（パスワード類はこちら）
- **Variable** は中身が見える設定値です

### 2-4. その他の前提

- ワークフローが **`main` ブランチ** にあること（定期実行はデフォルトブランチのみ対象）
- Settings → Actions → General で Actions の実行が許可されていること

### 動作確認

```sh
# トークンとページの接続確認（手元の PC で実行）
curl -s https://api.notion.com/v1/pages/<ページID> \
  -H "Authorization: Bearer <NOTION_TOKEN>" \
  -H "Notion-Version: 2022-06-28"
```

GitHub の **Actions タブ →「Notion → PostgreSQL 同期」→ Run workflow**（full にチェック）で手動実行し、ログに `✅ ○ 行 upsert` と出れば成功です。

---

## 3. Python ファイルで実行する理由

### 処理の流れ（`sync.py` が行っていること）

```
① ページ内の表を探す        find_tables()           … インライン DB / シンプルテーブルを判別
② 列名・型を取得する        get_database() / ヘッダー行 … build_column_map() / build_simple_table_columns()
③ テーブル・カラムを用意    ensure_table()          … CREATE TABLE / ALTER TABLE ADD COLUMN
④ 行データを取得・変換      query_pages() / property_value()
⑤ DB に書き込む             upsert_pages()          … 行 ID をキーに上書き（重複しない）
⑥ 削除された行を記録        _archived = true
```

### Python を選んだ理由

| 理由 | 内容 |
|---|---|
| 処理が多段階 | 上記 ①〜⑥ のように「API 取得 → 変換 → 表の作成 → 書き込み」があり、シェルスクリプトや SQL だけでは書きにくい |
| ライブラリが充実 | `requests`（Notion API 呼び出し）、`psycopg`（PostgreSQL 接続）が安定して使える |
| データ変換がしやすい | Notion の複雑な JSON（リッチテキスト・日付・マルチセレクトなど）を DB の型に変換する処理を簡潔に書ける |
| どこでも同じように動く | GitHub Actions・自分の PC・サーバーのどこでも `python notion_sync/sync.py` で実行できる。実行場所を変えてもコードは同じ |
| テストしやすい | `pytest` で実際の PostgreSQL を使った自動テストを用意している |

### ワークフロー（yml）と Python の役割分担

| | 担当 |
|---|---|
| yml（`notion_sync.yml`） | **いつ・どこで** 実行するか（時刻、Python の準備、環境変数の受け渡し） |
| Python（`sync.py`） | **何を** 実行するか（同期処理そのもの） |

yml に処理を書かず Python に分けているので、実行場所（GitHub Actions / PC の cron など）を変えても同期処理はそのまま使えます。

### 差分同期と全件同期

同じ `sync.py` でも `--full` の有無で処理が変わります（インラインデータベースのみ。シンプルテーブルは常に全行を同期）。

| 項目 | 差分（`--full` なし） | 全件（`--full` あり） |
|---|---|---|
| 取得する行 | 前回以降に変更された行だけ | 全行 |
| 追加・変更の反映 | ✅ | ✅ |
| 削除された行の反映 | ❌ | ✅（`_archived = true`） |
| 処理時間・API 負荷 | 小 | 行数に比例 |

初回は `--full` を付けなくても自動的に全件同期になります。

---

## 4. GitHub Actions を使用するメリット

| メリット | 内容 |
|---|---|
| **PC を閉じていても動く** | GitHub のサーバーで実行されるため、PC の電源状態に関係ない |
| **サーバー不要** | 自分でサーバーを借りたり管理したりする必要がない。実行のたびに新しい環境が用意され、終われば破棄される |
| **無料で使える** | 公開リポジトリは無料。非公開でも無料枠で十分（1 回あたり 1 分未満） |
| **コードと設定を一元管理** | スクリプト・実行スケジュール・履歴がすべて同じリポジトリにある |
| **実行履歴・ログが見られる** | Actions タブで成功 ✅ / 失敗 ❌ とログを確認できる（スマホからも可） |
| **失敗時にメール通知** | 既定で登録メールアドレスに通知が届く |
| **手動実行もできる** | Run workflow ボタンで好きなときに実行可能 |
| **秘密情報を安全に保管** | トークンや DB パスワードを Secrets で暗号化して保存できる |

### 定期実行の設定（現在の内容）

```yaml
on:
  schedule:
    - cron: "7 * * * *"     # 毎時 7 分：差分同期
    - cron: "47 17 * * *"   # 毎日 2:47（日本時間）：全件同期
  workflow_dispatch:         # 手動実行

concurrency:
  group: notion-sync        # 同時に 1 つだけ実行
  cancel-in-progress: false # 実行中は止めず、後から来たものを待たせる
```

- cron は「分 時 日 月 曜日」の順で、**時刻は UTC**（日本時間 −9 時間）
- 2 つの cron は分をずらしている（7 分 / 47 分）ので同時には起動しない。遅延で重なっても `concurrency` で順番に実行される
- 同じデータを 2 回書いても行 ID をキーに上書きするため、重複は発生しない

> **検討事項**：株価レポートは 1 日 1 回の更新のため、**毎日 1 回の全件同期だけ** にしても十分です。cron が 1 つになり構成がシンプルになります。

### 注意点

| 項目 | 内容 |
|---|---|
| `main` ブランチ限定 | 定期実行はデフォルトブランチのワークフローのみ対象 |
| 60 日ルール | 公開リポジトリで 60 日間コミット等の動きがないと定期実行が自動停止される（Actions 画面から再有効化） |
| 時刻のずれ | GitHub の混雑時は数分〜数十分遅れることがある。まれにスキップされることもある |
| 待機は 1 件まで | `concurrency` で待機中に新しい実行が来ると、待機中のものは取り消される（通常 1 分未満で終わるため実害はほぼない） |

---

## 5. Cloudflare で実行する場合に必要なこと

### Cloudflare のデータベース関連サービス

| サービス | 種類 | 今のコードでの扱い |
|---|---|---|
| **D1** | SQLite ベースのデータベース | そのままでは使えない（修正が必要） |
| **Hyperdrive** | Workers から外部 PostgreSQL へ高速接続する仕組み（DB ではない） | 保存先の PostgreSQL はそのまま使える |
| KV / R2 | キー・値ストア / ファイル置き場 | 表形式データには不向き |

Cloudflare 自身は PostgreSQL の DB サービスを提供していません（Supabase / Neon などに Hyperdrive で接続する形）。

### パターン A：同期は GitHub Actions、表示・利用を Cloudflare で（おすすめ）

```
Notion → GitHub Actions（sync.py）→ Supabase / Neon の PostgreSQL
                                          ↑
                       Cloudflare Workers（Hyperdrive 経由で読み取り）
```

- 同期の仕組みは **現状のまま**
- Cloudflare 側で株価表示サイトや API を作るときに使う

**必要なこと**

1. Cloudflare アカウント
2. Hyperdrive の設定（PostgreSQL の接続文字列を登録）
   ```sh
   npx wrangler hyperdrive create stock-db --connection-string="postgresql://..."
   ```
3. Workers の設定ファイル（`wrangler.toml`）に Hyperdrive を登録し、Workers のコード（JavaScript / TypeScript）から読み取る

### パターン B：保存先を Cloudflare D1 にする

```
Notion → GitHub Actions（sync.py を D1 対応に修正）→ Cloudflare D1
```

**必要なこと**

1. Cloudflare アカウントと D1 データベースの作成
   ```sh
   npx wrangler d1 create stock-db
   ```
2. GitHub Secrets の変更

   | 名前 | 値 |
   |---|---|
   | `CLOUDFLARE_ACCOUNT_ID` | Cloudflare のアカウント ID |
   | `CLOUDFLARE_D1_DATABASE_ID` | D1 のデータベース ID |
   | `CLOUDFLARE_API_TOKEN` | D1 の編集権限を持つ API トークン |

3. `sync.py` の修正（D1 は SQLite のため型や接続方法が異なる）

   | 今のコードで使っている機能 | D1（SQLite）での扱い |
   |---|---|
   | 配列型 `text[]`（マルチセレクトなど） | なし → JSON 文字列で保存 |
   | `jsonb` | なし → JSON 文字列で保存（JSON 関数で検索は可能） |
   | `timestamptz` / `numeric` | 専用の型なし → 文字列・数値で保存 |
   | スキーマ（`notion.` の区切り） | なし → テーブル名の接頭辞などで代用 |
   | psycopg で直接接続 | Cloudflare の HTTP API 経由に変更 |

- D1 は DB ごとの容量上限があり、大量の時系列データや複雑な集計は PostgreSQL より苦手

### パターン C：同期処理そのものを Cloudflare Workers で定期実行

GitHub Actions の代わりに **Workers の Cron Triggers** で実行する方法です。

**必要なこと**

1. 同期処理を Workers 用に **書き直す**（主に JavaScript / TypeScript）
   - 今の `sync.py` は `psycopg` などのライブラリを使っているため、Workers ではそのまま動きません
2. `wrangler.toml` に定期実行を設定
   ```toml
   [triggers]
   crons = ["47 17 * * *"]   # UTC
   ```
3. トークンを Workers のシークレットに登録
   ```sh
   npx wrangler secret put NOTION_TOKEN
   ```
4. 保存先を D1（バインディング）または Hyperdrive 経由の PostgreSQL に接続
5. Workers の実行時間・CPU 時間の制限に収まるよう、大きな表は分割して処理する

### 比較

| | 同期の実行場所 | 保存先 | 既存コードの修正 | おすすめ度 |
|---|---|---|---|---|
| 現状 | GitHub Actions | クラウド PostgreSQL | 不要 | ◎ |
| A | GitHub Actions | クラウド PostgreSQL（Cloudflare から読む） | 不要 | ◎ |
| B | GitHub Actions | Cloudflare D1 | `sync.py` の保存部分を修正 | ○（データ量が少ない場合） |
| C | Cloudflare Workers | D1 / PostgreSQL | 全面的に書き直し | △ |

**株価の蓄積・分析が目的なら、現状構成（＋必要に応じてパターン A）が最も手間が少なく機能も十分です。**

※ Cloudflare のサービス内容・制限は変更されることがあるため、利用前に公式ドキュメントで確認してください。
