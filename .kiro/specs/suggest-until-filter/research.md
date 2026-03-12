# Research & Design Decisions

## Summary
- **Feature**: `suggest-until-filter`
- **Discovery Scope**: Extension
- **Key Findings**:
  - yt-dlpは `release_timestamp`（Unixタイムスタンプ）を提供しており、ライブ配信の開始日時を取得可能
  - 現在のDBスキーマ（version 1）は `published_at`（`upload_date`由来）のみを保持
  - SQLiteの `ALTER TABLE ADD COLUMN` で既存DBへのカラム追加が可能（デフォルト値NULLで安全に追加可能）

## Research Log

### yt-dlpの配信開始日時フィールド
- **Context**: 配信開始日時として使用可能なyt-dlpフィールドの調査
- **Sources Consulted**: yt-dlpソースコード、既存の`fetch_video_metadata()`実装
- **Findings**:
  - `release_timestamp`: Unixタイムスタンプ（秒）。ライブ配信の実際の開始日時を返す
  - `release_date`: YYYYMMDD形式の日付文字列
  - `upload_date`: YYYYMMDD形式。動画の公開日（現在`published_at`に使用中）
  - ライブ配信以外の動画では `release_timestamp` がNoneの場合がある
- **Implications**: `release_timestamp` を優先的に使用し、取得不可時は `published_at` をフォールバックする設計が適切

### SQLiteスキーママイグレーション
- **Context**: 既存DBへの `broadcast_start_at` カラム追加方法
- **Findings**:
  - `ALTER TABLE videos ADD COLUMN broadcast_start_at TEXT` で安全に追加可能
  - 既存行のデフォルト値はNULL
  - インデックス追加も後から可能
  - `schema_version` テーブルで現在のバージョン（1）を管理済み
- **Implications**: `initialize()` 内でバージョンチェック→マイグレーション実行の既存パターンを拡張

### 既存動画のバックフィル方式
- **Context**: DBに保存済みの動画の配信開始日時をどう一括更新するか
- **Findings**:
  - `broadcast_start_at IS NULL` の動画を対象にyt-dlpでメタデータ再取得
  - yt-dlpの `extract_info()` は `skip_download: True` で軽量に実行可能
  - 1件ずつ処理し、エラー時も継続する耐障害設計が必要
- **Implications**: CLIサブコマンドとして提供し、ユーザーが明示的に実行する形式が適切

## Design Decisions

### Decision: 配信開始日時カラム名
- **Context**: DB保存用のカラム名選定
- **Alternatives Considered**:
  1. `broadcast_start_at` — 配信開始を明示
  2. `release_timestamp` — yt-dlpフィールド名と一致
  3. `streamed_at` — 簡潔
- **Selected Approach**: `broadcast_start_at`
- **Rationale**: 既存の`published_at`・`synced_at`の命名規則（`_at`サフィックス）と一貫性があり、「配信開始」の意味が明確
- **Trade-offs**: yt-dlpフィールド名と異なるが、ドメイン名として自然

### Decision: バックフィルコマンドの配置
- **Context**: 既存動画の配信開始日時を更新するコマンドをどこに配置するか
- **Alternatives Considered**:
  1. `kirinuki migrate backfill-broadcast-start` — migrateサブグループ
  2. `kirinuki backfill` — トップレベルコマンド
  3. `kirinuki sync --backfill-broadcast-start` — syncのオプション
- **Selected Approach**: `kirinuki migrate backfill-broadcast-start`
- **Rationale**: 一度だけ実行するマイグレーション的な操作であり、`migrate` グループにまとめることで将来の同種コマンド追加にも対応可能。syncとは責務が異なる
- **Trade-offs**: 新しいCLIグループの導入が必要

### Decision: --until の日時パース戦略
- **Context**: ユーザーが入力する日時文字列のパース方法
- **Alternatives Considered**:
  1. clickの `DateTime` 型 — 限られたフォーマットのみ
  2. `dateutil.parser.parse()` — 柔軟だが依存追加
  3. カスタムパーサー（複数フォーマットのtryparse） — 依存なし
- **Selected Approach**: カスタムパーサー（`YYYY-MM-DD` と `YYYY-MM-DD HH:MM` の2形式）
- **Rationale**: 依存追加なし、ユーザーに明確なフォーマットを提示でき、エラー時のガイダンスも容易
- **Trade-offs**: 対応形式が限定的だが、実用上十分

## Risks & Mitigations
- yt-dlpの `release_timestamp` がNoneの動画が多い可能性 → `published_at` フォールバックで対応
- バックフィル時のYouTube APIレート制限 → 1件ずつ逐次処理で負荷抑制
- 大量動画のバックフィルに時間がかかる可能性 → 進捗表示と中断耐性で対応
