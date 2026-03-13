# kirinuki

YouTube Live 配信アーカイブの字幕を蓄積し、LLM で話題区間を自動セグメント化、複数動画を横断検索できる CLI ツール。

動画本体はローカルに保存せず、字幕・メタデータのみを蓄積します。切り抜きが必要になったときだけオンデマンドで動画を取得し、指定区間を切り出します。

## できること

- チャンネルを登録して字幕・メタデータを自動同期
- LLM による話題セグメンテーション（どこで何を話していたかを自動抽出）
- 複数動画を横断したセマンティック検索
- 切り抜き候補の自動推薦
- 指定区間のクリッピング（yt-dlp の部分DLで必要フラグメントのみ取得）
- 複数箇所の一括切り抜き（カンマ区切りで時間範囲を指定）
- メンバー限定配信対応（Cookie 認証）

## 必要なもの

### ソースから使う場合

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Node.js](https://nodejs.org/) 20.0.0+（yt-dlp の YouTube JS 処理に必要、セキュリティ上 25+ を強く推奨）
- [ffmpeg](https://ffmpeg.org/)（切り抜き機能を使う場合）
- Anthropic API キー（話題セグメンテーション・推薦用）
- OpenAI API キー（埋め込みベクトル生成・セマンティック検索用）

### ビルド済みバイナリを使う場合

- [Node.js](https://nodejs.org/) 20.0.0+（yt-dlp の YouTube JS 処理に必要、セキュリティ上 25+ を強く推奨）
- [ffmpeg](https://ffmpeg.org/)（切り抜き機能を使う場合）
- Anthropic API キー（話題セグメンテーション・推薦用）
- OpenAI API キー（埋め込みベクトル生成・セマンティック検索用）

Python や uv のインストールは不要です。

## インストール

### ビルド済みバイナリを使う場合（おすすめ）

1. Releases から `kirinuki.exe` をダウンロード
2. PATH の通ったディレクトリに配置する（例: `C:\Users\<ユーザー名>\bin\`）
3. そのまま `kirinuki` コマンドとして使えます

### ソースから使う場合

```bash
git clone <repository-url>
cd kirinuki/initial
uv sync
```

ソースから使う場合は、すべてのコマンドを `uv run kirinuki ...` の形式で実行してください。

## 設定

環境変数または `~/.kirinuki/.env` ファイルで設定します。接頭辞は `KIRINUKI_` です。

```bash
# ~/.kirinuki/.env に記載する場合
KIRINUKI_ANTHROPIC_API_KEY="sk-ant-..."
KIRINUKI_OPENAI_API_KEY="sk-..."

# 任意
KIRINUKI_DB_PATH="/path/to/data.db"               # デフォルト: ~/.kirinuki/data.db
KIRINUKI_OUTPUT_DIR="/path/to/output"              # デフォルト: ~/.kirinuki/output
KIRINUKI_LLM_MODEL="claude-haiku-4-5-20251001"    # デフォルト
KIRINUKI_EMBEDDING_MODEL="text-embedding-3-small"  # デフォルト
```

環境変数でも同様に設定できます（`export KIRINUKI_ANTHROPIC_API_KEY="sk-ant-..."` など）。環境変数が `.env` より優先されます。

## 使い方

> ソースから使う場合は、各コマンドの先頭に `uv run` を付けてください（例: `uv run kirinuki channel list`）。

### チャンネル登録

```bash
# チャンネルを登録
kirinuki channel add https://www.youtube.com/@channel_name

# 登録済みチャンネル一覧
kirinuki channel list

# チャンネルの動画一覧（チャンネルが1つなら省略可）
kirinuki channel videos [channel_id]
```

### 動画一覧

```bash
# 全チャンネル横断で動画一覧を新しい順に表示
kirinuki videos

# 表示件数を指定
kirinuki videos --count 10

# TUIモード: 動画を選択して segments/suggest を実行
kirinuki videos --tui
```

| オプション | デフォルト | 説明 |
|---|---|---|
| `--count` | 20 | 表示件数 |
| `--tui` | off | TUI モードで動画を選択し、segments/suggest を実行 |

### 字幕の同期

```bash
# 全登録チャンネルの字幕を差分同期
kirinuki sync

# セグメントの最大長を指定して同期（デフォルト: 300000ms = 5分）
kirinuki sync --max-segment-ms 600000
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

### セグメントの再生成

```bash
# プロンプトが更新された動画のセグメントを再生成
kirinuki resegment

# 特定の動画だけ再生成
kirinuki resegment --video-id <video_id>

# 全動画を強制的に再生成
kirinuki resegment --force

# セグメント最大長を指定
kirinuki resegment --max-segment-ms 600000
```

### 利用不可動画のリセット

取得時に「利用不可」となった動画の記録をリセットし、次回 sync 時に再取得を試みます。

```bash
# 全チャンネルの利用不可レコードをリセット
kirinuki unavailable reset

# 特定チャンネルのみリセット
kirinuki unavailable reset --channel <channel_id>
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

### 切り抜き

```bash
# 単一区間の切り抜き
kirinuki clip <動画IDまたはURL> <出力ファイル名> <時間範囲>
kirinuki clip dQw4w9WgXcQ output.mp4 18:03-19:31

# 複数区間を一括切り抜き（カンマ区切り）
kirinuki clip dQw4w9WgXcQ highlight.mp4 18:03-19:31,21:31-23:20,45:00-46:30
# → highlight1.mp4, highlight2.mp4, highlight3.mp4 が生成される

# 出力先ディレクトリを指定（デフォルト: ~/.kirinuki/output）
kirinuki clip dQw4w9WgXcQ output.mp4 1:00:00-1:05:00 --output-dir ./clips

# YouTube URLも使用可能
kirinuki clip https://www.youtube.com/watch?v=dQw4w9WgXcQ clip.mp4 5:00-10:00
```

yt-dlp の部分ダウンロード機能を利用し、指定範囲のフラグメントのみを取得します。動画全体をダウンロードしないため、長時間配信からの切り抜きでも高速です。

メンバー限定動画の場合は Cookie が自動的に使用されます（`kirinuki cookie set` で事前に設定が必要）。

| オプション | デフォルト | 説明 |
|---|---|---|
| `--output-dir` | `~/.kirinuki/output` | 出力先ディレクトリ（設定ファイルでも指定可能） |

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
| `--until` | なし | 配信開始日時の上限（`YYYY-MM-DD` または `YYYY-MM-DD HH:MM`） |
| `--json` | off | JSON 形式で出力 |

### データベースマイグレーション

```bash
# 既存動画の配信開始日時を一括取得・更新
kirinuki migrate backfill-broadcast-start
```

`--until` オプションで使われる `broadcast_start_at` が未設定の既存動画に対して、YouTube から配信開始日時を取得して DB を更新します。

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

# スタンドアロンバイナリのビルド
uv run pyinstaller kirinuki.spec
# 成果物: dist/kirinuki.exe
```

## ライセンス

TBD
