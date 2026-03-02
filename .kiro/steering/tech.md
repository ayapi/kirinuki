# Technology Stack

## Architecture

CLIアプリケーション。モジュラー構成で「取得」「字幕解析」「検索」「クリッピング」の各責務を分離。
外部ツール（yt-dlp, ffmpeg）はラッパーパターン、LLM連携はサービス層で抽象化。
ローカルSQLiteに動画メタデータ・字幕・ベクトルインデックスを永続化。

### ストレージ戦略（遅延ダウンロード）
- **永続保存**: 字幕データ、メタデータ、インデックスのみ（SQLite）
- **動画は保存しない**: 切り抜き実行時にオンデマンドでDL → 指定区間を切り出し → 元動画を即時削除
- **ローカルに残るもの**: DB + 生成された切り抜き動画のみ

## Platform

- **対応OS**: Windows（MSYS2/Git Bash）、Linux、macOS
- Windows環境ではMSYS2（Git Bash）上での動作を前提とする
- TUIライブラリ等、クロスプラットフォーム対応のものを選定

## Core Technologies

- **Language**: Python 3.12+
- **Package Manager**: uv（高速な依存管理）
- **Runtime**: CPython

### 選定理由（Python）
- yt-dlp（YouTubeダウンロードのデファクト標準）がPythonネイティブで、ライブラリとしても直接利用可能
- メンバー限定動画のCookie認証処理がyt-dlpに内蔵
- ffmpeg連携もsubprocessまたはffmpeg-pythonで成熟したエコシステムがある
- CLIツールとしてPythonは適切な選択

## Key Libraries

### 動画取得・処理
- **yt-dlp** — YouTube動画・字幕ダウンロード（メンバー限定対応、字幕取得含む）
- **ffmpeg**（subprocess） — 動画クリッピング・エンコード
- **google-api-python-client** — YouTube Data API v3（メタデータ取得）

### 字幕解析・検索
- **anthropic** — Claude API（話題セグメンテーション、要約、推薦）
- **openai** — OpenAI Embeddings API（セマンティック検索用ベクトル生成）
- **sqlite3**（標準ライブラリ） — メタデータ・字幕・インデックスの永続化
- **sqlite-vec** — SQLite拡張によるベクトル検索（意味検索用、ローカル完結）

### CLI・基盤
- **click** — CLIフレームワーク（サブコマンド・オプション定義）
- **pydantic** / **pydantic-settings** — データモデルのバリデーション・環境変数ベースの設定管理
- **beaupy** — TUIインタラクティブ選択メニュー（クロスプラットフォーム対応、Windows含む）

## Development Standards

### Type Safety
- 型ヒント必須（`mypy --strict` または `pyright`）
- Pydanticモデルでランタイムバリデーション

### Code Quality
- **Linter**: Ruff（Flake8互換 + isort + Black相当）
- **Formatter**: Ruff format
- 全コード `ruff check` と `ruff format --check` をパス

### Testing
- **Framework**: pytest
- 外部ツール（yt-dlp, ffmpeg）呼び出しはモック化
- ユニットテストとインテグレーションテストの分離

## Development Environment

### Required Tools
- Python 3.12+
- uv（パッケージマネージャ）
- ffmpeg（システムインストール）
- Node.js（yt-dlpのJS処理に必要）
- yt-dlp（Python依存で管理）

### Windows環境
- MSYS2（Git Bash）推奨
- `windows-curses`不要（beaupyはcursesを使わない）
- パス区切りはPythonの`pathlib`で吸収

### Common Commands
```bash
# Setup: uv sync
# Dev: uv run python -m kirinuki
# Test: uv run pytest
# Lint: uv run ruff check .
# Format: uv run ruff format .
# Type check: uv run mypy src/
```

## Key Technical Decisions

| 決定事項 | 選択 | 理由 |
|---------|------|------|
| 言語 | Python | yt-dlpネイティブ連携、CLI向き |
| パッケージ管理 | uv | 高速、lockfile対応、PEP準拠 |
| 動画DL・字幕 | yt-dlp（ライブラリ） | subprocess不要、認証統合、字幕DL対応 |
| ストレージ戦略 | 遅延DL + 即時削除 | 字幕のみ蓄積、動画はオンデマンド取得・使い捨て |
| 動画処理 | ffmpeg（subprocess） | 信頼性、柔軟性 |
| LLM | Claude API | 日本語の話題理解、セグメンテーション |
| データ永続化 | SQLite | ゼロ設定、単一ファイル、FTS5全文検索対応 |
| Embeddings | OpenAI Embeddings API | 高品質な日本語ベクトル生成 |
| ベクトル検索 | sqlite-vec | SQLite拡張、軽量でローカル完結 |
| CLI | click | 宣言的、サブコマンド対応 |
| TUI | beaupy | クロスプラットフォーム、マルチセレクト対応 |
| バリデーション | Pydantic v2 + pydantic-settings | 型安全、環境変数ベース設定管理 |

---
_Document standards and patterns, not every dependency_
