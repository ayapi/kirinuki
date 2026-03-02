# Project Structure

## Organization Philosophy

**レイヤー分離型**のモジュラー構成。CLI → コア（ドメインロジック） → インフラ（外部連携）の3層。
字幕解析・検索・クリッピングを独立したドメインとして扱い、インフラ層でLLM・DB・外部ツールへの依存を吸収。

## Directory Patterns

### ソースコード
**Location**: `src/kirinuki/`
**Purpose**: アプリケーション本体。Pythonパッケージとして構成
**Example**: `src/kirinuki/__init__.py`

### CLI層
**Location**: `src/kirinuki/cli/`
**Purpose**: CLIコマンド定義。入力パース→コア呼び出し→結果表示のみ。TUIモード対応のコマンドはアダプター→TUIセレクター→実行の共通フローを使用
**Example**: `cli/main.py`（コマンド群）、`cli/suggest.py`（suggestサブコマンド）、`cli/tui.py`（TUIアダプター・セレクター・実行）、`cli/cookie.py`（Cookie管理）

### コアロジック
**Location**: `src/kirinuki/core/`
**Purpose**: ドメインロジック。外部ツール・API非依存
**Example**:
- `core/segmentation_service.py` — 字幕→話題セグメンテーション
- `core/search_service.py` — 検索クエリ処理、結果ランキング
- `core/clip_service.py` — 切り抜き実行（時間範囲指定、複数区間対応）
- `core/suggest.py` — LLMベースの切り抜き候補推薦
- `core/clip_utils.py` — ファイル名生成、URL解析等のユーティリティ

### インフラ層（外部連携）
**Location**: `src/kirinuki/infra/`
**Purpose**: 外部サービス・ツールとのインテグレーション。交換可能なアダプター
**Example**:
- `infra/ytdlp_client.py` — yt-dlpラッパー（動画・字幕DL）
- `infra/ffmpeg.py` — ffmpegラッパー（動画クリッピング）
- `infra/llm_client.py` — Claude APIクライアント（セグメンテーション・推薦）
- `infra/database.py` — SQLiteアクセス（メタデータ・字幕・インデックス永続化）
- `infra/embedding_provider.py` — OpenAI Embeddings APIクライアント（ベクトル生成）

### データモデル
**Location**: `src/kirinuki/models/`
**Purpose**: Pydanticモデル定義（設定、ドメインオブジェクト、コマンド間受け渡し）
**Example**: `models/config.py`（AppConfig）、`models/domain.py`（SearchResult, Segment）、`models/clip.py`（TimeRange, ClipOutcome）、`models/tui.py`（ClipCandidate）、`models/recommendation.py`（SuggestResult）

### テスト
**Location**: `tests/`
**Purpose**: pytestテスト。ソース構造をミラー
**Example**: `tests/core/test_subtitle.py`, `tests/infra/test_ytdlp.py`

## Naming Conventions

- **ファイル**: snake_case（`clip_spec.py`, `youtube_api.py`）
- **クラス**: PascalCase（`ClipSpec`, `VideoMetadata`）
- **関数・変数**: snake_case（`download_video`, `clip_range`）
- **定数**: UPPER_SNAKE_CASE（`DEFAULT_FORMAT`, `MAX_RETRIES`）

## Import Organization

```python
# 1. 標準ライブラリ
from pathlib import Path

# 2. サードパーティ
from pydantic import BaseModel

# 3. ローカル（相対インポート推奨）
from kirinuki.core.clip_spec import ClipSpec
from kirinuki.infra.ytdlp import YtdlpClient
```

## Code Organization Principles

- **CLI層は薄く**: パース→コア呼び出し→結果表示のみ
- **TUIはアダプターパターン**: 異なる結果型（SearchResult, Segment, SuggestResult）を共通のClipCandidateに変換し、統一的なTUI選択→切り抜き実行フローを通す
- **コア層は外部非依存**: yt-dlp、ffmpeg、LLM APIを直接importしない。インフラ層のインターフェースに依存
- **インフラ層は交換可能**: 外部ツール・APIのラッパーを提供し、テスト時にモック差し替え可能
- **データはローカル完結**: SQLiteで単一ファイル管理、外部DBサーバー不要
- **動画は使い捨て**: 動画ファイルは一時ディレクトリにDL → 切り抜き生成 → 元ファイル即時削除。永続保存するのは字幕・メタデータ・切り抜き結果のみ
- **設定は集約**: Pydanticモデルで一箇所に定義、環境変数ベース（pydantic-settings）

---
_Document patterns, not file trees. New files following patterns shouldn't require updates_
