# kirinuki

YouTube Live 配信アーカイブの字幕を蓄積し、LLM で話題区間を自動セグメント化、複数動画を横断検索できる CLI ツール。

動画本体はローカルに保存せず、字幕・メタデータのみを蓄積します。切り抜きが必要になったときだけオンデマンドで動画を取得し、指定区間を切り出します。

## できること

- チャンネルを登録して字幕・メタデータを自動同期
- LLM による話題セグメンテーション（どこで何を話していたかを自動抽出）
- 複数動画を横断したセマンティック検索
- 切り抜き候補の自動推薦
- 指定区間のクリッピング（オンデマンドDL → 切り出し → 元動画即削除）
- メンバー限定配信対応（Cookie 認証）

## 必要なもの

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/)（切り抜き機能を使う場合）
- Anthropic API キー（話題セグメンテーション・推薦用）
- OpenAI API キー（埋め込みベクトル生成・セマンティック検索用）

## インストール

```bash
git clone <repository-url>
cd kirinuki/initial
uv sync
```

## 設定

環境変数で設定します。接頭辞は `KIRINUKI_` です。

```bash
export KIRINUKI_ANTHROPIC_API_KEY="sk-ant-..."
export KIRINUKI_OPENAI_API_KEY="sk-..."

# 任意
export KIRINUKI_DB_PATH="/path/to/data.db"               # デフォルト: ~/.kirinuki/data.db
export KIRINUKI_LLM_MODEL="claude-haiku-4-5-20251001"    # デフォルト
export KIRINUKI_EMBEDDING_MODEL="text-embedding-3-small"  # デフォルト
```

## 使い方

### チャンネル登録

```bash
# チャンネルを登録
kirinuki channel add https://www.youtube.com/@channel_name

# 登録済みチャンネル一覧
kirinuki channel list

# チャンネルの動画一覧（チャンネルが1つなら省略可）
kirinuki channel videos [channel_id]
```

### 字幕の同期

```bash
# 全登録チャンネルの字幕を差分同期
kirinuki sync
```

登録チャンネルの動画から字幕とメタデータを取得し、ローカル DB に蓄積します。同期済みの動画はスキップされます。

### 検索

```bash
# 全動画を横断検索
kirinuki search "雑談で話してたゲームの話"

# 件数指定
kirinuki search "コラボ配信" --limit 5
```

### 話題セグメントの確認

```bash
# 動画の話題区間一覧を表示
kirinuki segments <video_id>
```

### Cookie 管理

メンバー限定配信を取得するには Cookie の設定が必要です。Cookie は `~/.kirinuki/cookies.txt` に保存されます。

```bash
# Cookie を設定（実行後にペーストして Ctrl+D / Windows: Ctrl+Z → Enter で確定）
kirinuki cookie set

# Cookie の設定状態を確認
kirinuki cookie status

# Cookie を削除
kirinuki cookie delete
```

### 切り抜き候補の推薦

```bash
# チャンネルの最新アーカイブから切り抜き候補を推薦（チャンネルが1つなら省略可）
kirinuki suggest [channel_id]

# オプション指定
kirinuki suggest [channel_id] --count 5 --threshold 5

# JSON出力
kirinuki suggest [channel_id] --json
```

| オプション | デフォルト | 説明 |
|---|---|---|
| `--count` | 3 | 対象アーカイブ件数 |
| `--threshold` | 7 | 推薦スコア閾値（1〜10） |
| `--json` | off | JSON 形式で出力 |

## 開発

```bash
# テスト
uv run pytest

# Lint
uv run ruff check .

# フォーマット
uv run ruff format .

# 型チェック
uv run mypy src/
```

## ライセンス

TBD
