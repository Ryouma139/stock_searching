# Notion DB → PostgreSQL 同期

Notion のデータベースを PostgreSQL に移行し、その後も定期的に自動同期する仕組みです。
設計の背景や検討内容（クラウド DB・GitHub Actions・Cloudflare など）は [GUIDE.md](GUIDE.md) にまとめています。

- 初回実行で全ページを取り込み（= 移行）、以降は **毎時の差分同期** と **毎日の全件同期** を GitHub Actions で自動実行します
- **Notion の表 1 つ → PostgreSQL のテーブル 1 つ、表の 1 行 → 1 レコード** として移行します
- ページを指定すると、ページ内の表を自動で見つけて移行します（トグルやカラムレイアウトの中にある表も対象）
- テーブル・カラムは Notion の表の列から自動作成されます。Notion 側で列を追加すると次回同期でカラムも追加されます

## 対応している表

| Notion の表 | 作り方 | PostgreSQL での扱い |
|---|---|---|
| インラインデータベース | `/database` や「データベース - インライン」 | 列の型（数値・日付・セレクトなど）を保って移行。毎時は変更行だけ差分同期 |
| シンプルテーブル | `/table` | 1 行目（ヘッダー行）の文字を列名に、全列 `text` で移行。毎回全行を同期 |

テーブル名は、インライン DB はそのタイトル、シンプルテーブルは直前の見出し（なければページ名）から付けます。

## セットアップ

1. **Notion インテグレーションを作成**
   <https://www.notion.so/profile/integrations> で内部インテグレーションを作り、シークレットを控える。
   同期したい DB を開き「… → 接続 → 作成したインテグレーション」を追加する。
2. **対象ページの URL をコピー**
   ページ右上「…」→「リンクをコピー」。URL をそのまま設定できます（ID だけでも可）。
   インライン DB を単体で指定したい場合は、DB の「…」→「ビューのリンクをコピー」の URL を `NOTION_DATABASE_IDS` に設定します。
3. **GitHub リポジトリに設定**（Settings → Secrets and variables → Actions）

   | 種類 | 名前 | 値 |
   |---|---|---|
   | Secret | `NOTION_TOKEN` | インテグレーションのシークレット |
   | Secret | `DATABASE_URL` | `postgresql://user:pass@host:5432/dbname`（GitHub から接続できるホスト） |
   | Variable | `NOTION_PAGE_IDS` | 表を含むページの URL または ID。複数はカンマ区切り |
   | Variable | `NOTION_DATABASE_IDS` | 任意。DB を直接指定する場合の URL または ID。`ID:テーブル名` で名前指定可 |
   | Variable | `PG_SCHEMA` | 任意。格納先スキーマ（既定 `notion`） |

4. Actions タブ →「Notion → PostgreSQL 同期」→ **Run workflow**（full にチェック）で初回移行を実行。

## ローカル実行

```sh
pip install -r notion_sync/requirements.txt
export NOTION_TOKEN=secret_xxx
export NOTION_PAGE_IDS=https://www.notion.so/xxxx/<ページID>
export DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
python notion_sync/sync.py --full   # 初回・全件
python notion_sync/sync.py          # 差分
```

cron で動かす場合の例（毎時差分・毎晩全件）:

```cron
7 * * * *  cd /path/to/stock_searching && python notion_sync/sync.py >> sync.log 2>&1
47 2 * * * cd /path/to/stock_searching && python notion_sync/sync.py --full >> sync.log 2>&1
```

## テーブル構成

### インラインデータベース

`<スキーマ>.<テーブル名>` に表の 1 行 = 1 レコードで保存します（Notion の DB の行は内部的に 1 ページとして扱われるため、行 ID は「ページ ID」になります）。

| カラム | 内容 |
|---|---|
| `_page_id` | Notion ページ ID（主キー） |
| `_url` / `_created_time` / `_last_edited_time` | ページのメタ情報 |
| `_archived` | Notion 側で削除・アーカイブされたら `true`（行は消さない） |
| `_properties` | Notion の全プロパティの生 JSON |
| `_synced_at` | 最終同期時刻 |
| Notion の各プロパティ | 下表の型で 1 カラムずつ |

| Notion 型 | PostgreSQL 型 |
|---|---|
| タイトル・テキスト・セレクト・ステータス・URL・メール・電話・ID | `text` |
| 数値 | `numeric` |
| チェックボックス | `boolean` |
| 日付（`<名前>_end` に終了日） | `timestamptz` |
| マルチセレクト・ユーザー・リレーション・ファイル | `text[]` |
| 数式・ロールアップ | `jsonb` |

### シンプルテーブル

| カラム | 内容 |
|---|---|
| `_row_id` | Notion の行 ID（主キー） |
| `_row_index` | 表の中での並び順（0 始まり、ヘッダー行を除く） |
| `_last_edited_time` | 行の最終更新時刻 |
| `_archived` | Notion 側で行が削除されたら `true` |
| `_synced_at` | 最終同期時刻 |
| ヘッダー行の各列 | すべて `text`（ヘッダーが空の列は `col_N`） |

同期状態は `<スキーマ>._sync_state` に DB ごとに記録されます。

## 注意

- シンプルテーブルのヘッダー名を変えると、新しい名前のカラムが追加されます（旧カラムは残るので不要なら削除してください）
- Notion 側でプロパティの型を変えると、既存カラムと型が合わない場合はそのカラムの更新をスキップします（値は `_properties` には入ります）。必要ならカラムを削除すれば次回同期で作り直されます
- Notion API バージョン `2022-06-28` を使用しています。複数データソースを持つ DB（2025 年以降の新機能）は非対応です

## テスト

```sh
TEST_DATABASE_URL=postgresql://postgres@localhost/postgres python -m pytest notion_sync/tests
```
