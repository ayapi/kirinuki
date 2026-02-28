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
**Purpose**: CLIコマンド定義。入力パース→コア呼び出し→結果表示のみ
**Example**: `src/kirinuki/cli/clip.py`, `src/kirinuki/cli/search.py`

### コアロジック
**Location**: `src/kirinuki/core/`
**Purpose**: ドメインロジック。外部ツール・API非依存
**Example**:
- `core/subtitle.py` — 字幕パース、話題セグメンテーションのロジック
- `core/search.py` — 検索クエリ処理、結果ランキング
- `core/clip.py` — 切り抜き仕様（時間範囲、品質設定等）

### インフラ層（外部連携）
**Location**: `src/kirinuki/infra/`
**Purpose**: 外部サービス・ツールとのインテグレーション。交換可能なアダプター
**Example**:
- `infra/ytdlp.py` — yt-dlpラッパー（動画・字幕DL）
- `infra/ffmpeg.py` — ffmpegラッパー（動画クリッピング）
- `infra/llm.py` — LLM APIクライアント（話題分析・推薦）
- `infra/db.py` — SQLiteアクセス（メタデータ・字幕・インデックス永続化）

### データモデル
**Location**: `src/kirinuki/models/`
**Purpose**: Pydanticモデル定義（設定、ドメインオブジェクト、DB行マッピング）
**Example**: `models/config.py`, `models/video.py`, `models/segment.py`

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
- **コア層は外部非依存**: yt-dlp、ffmpeg、LLM APIを直接importしない。インフラ層のインターフェースに依存
- **インフラ層は交換可能**: 外部ツール・APIのラッパーを提供し、テスト時にモック差し替え可能
- **データはローカル完結**: SQLiteで単一ファイル管理、外部DBサーバー不要
- **動画は使い捨て**: 動画ファイルは一時ディレクトリにDL → 切り抜き生成 → 元ファイル即時削除。永続保存するのは字幕・メタデータ・切り抜き結果のみ
- **設定は集約**: Pydanticモデルで一箇所に定義、環境変数・設定ファイル両対応

---
_Document patterns, not file trees. New files following patterns shouldn't require updates_
