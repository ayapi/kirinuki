# Research & Design Decisions

## Summary
- **Feature**: `sync-retry-segmentation`
- **Discovery Scope**: Extension（既存sync処理の拡張）
- **Key Findings**:
  - セグメンテーション状態は`segments`テーブルの行の有無で推定可能（明示的なステータスカラムなし）
  - 再試行に必要なデータ（`subtitle_lines`、`videos.duration_seconds`）はすべてDB保存済み
  - YouTube APIへの再アクセスは不要

## Research Log

### セグメンテーション状態の追跡方法
- **Context**: セグメンテーション未完了の動画をどう検出するか
- **Sources Consulted**: `src/kirinuki/infra/database.py`（スキーマ定義）、`src/kirinuki/core/segmentation_service.py`
- **Findings**:
  - `videos`テーブルにセグメンテーション状態カラムは存在しない
  - `segments`テーブルに行があればセグメンテーション完了、なければ未完了と推定できる
  - `list_segments(video_id)`が空リストを返す場合、セグメンテーション未実行
- **Implications**: 新しいカラムを追加せず、LEFT JOINで未セグメント動画を検出するクエリで対応可能

### 再試行に必要なデータの所在
- **Context**: 再試行時にYouTubeからの再取得が不要であることの確認
- **Sources Consulted**: `src/kirinuki/infra/database.py`、`src/kirinuki/core/sync_service.py`
- **Findings**:
  - `subtitle_lines`テーブル: `video_id`, `start_ms`, `duration_ms`, `text`を保持
  - `videos`テーブル: `duration_seconds`を保持（チャンク分割判定に使用）
  - `segment_video_from_entries(video_id, entries, duration_seconds)`が再試行のエントリーポイント
  - `SubtitleEntry`モデル: `start_ms`, `duration_ms`, `text`のフィールドで`subtitle_lines`テーブルと1:1対応
- **Implications**: DBから`SubtitleEntry`リストと`duration_seconds`を取得すれば、既存の`segment_video_from_entries()`をそのまま使える

### SyncResult拡張の影響範囲
- **Context**: 再試行結果をサマリーに反映するための変更範囲
- **Sources Consulted**: `src/kirinuki/models/domain.py`、`src/kirinuki/cli/main.py`
- **Findings**:
  - `SyncResult`はPydanticモデルでデフォルト値付きフィールドを持つ
  - フィールド追加は後方互換（デフォルト値0で既存コードに影響なし）
  - CLI表示部分（`sync`コマンド）に再試行結果表示を追加する必要がある
  - `sync_all()`内で各チャンネルの結果を集約する箇所にも追加が必要

## Design Decisions

### Decision: 明示的ステータスカラム vs クエリベース検出
- **Context**: セグメンテーション未完了動画の検出方法
- **Alternatives Considered**:
  1. `videos`テーブルに`segmentation_status`カラムを追加する
  2. `segments`テーブルとのLEFT JOINで検出する
- **Selected Approach**: LEFT JOINクエリベース検出
- **Rationale**: スキーマ変更不要（マイグレーション不要）。`segments`テーブルに行がない＝セグメンテーション未完了は一意に判定可能。既存の`list_segments()`の仕組みとも一貫性がある
- **Trade-offs**: クエリが若干複雑だが、スキーマ変更のコストを回避できる
- **Follow-up**: 大量の動画がある場合のクエリパフォーマンスを確認

### Decision: 再試行のタイミング
- **Context**: sync_channel内のどの時点で再試行を実行するか
- **Alternatives Considered**:
  1. 新規動画処理の前に再試行する
  2. 新規動画処理の後に再試行する
- **Selected Approach**: 新規動画処理の後に再試行
- **Rationale**: 新規動画のセグメンテーションが先に完了することで、APIクレジットが足りない場合の影響を新規動画側で早期検知できる。再試行は「追加処理」として位置づけるのが自然
- **Trade-offs**: 新規動画の処理でAPIクレジットを使い切ると再試行も失敗する可能性があるが、次回syncで再度試行されるため問題ない

## Risks & Mitigations
- APIクレジット不足が継続する場合、毎回再試行→失敗を繰り返す — 再試行失敗はログに記録され、次回もリトライ対象として残るため、APIクレジット回復後に自動解消
- subtitle_linesが保存されていない動画（旧バージョンで取得した等）— subtitle_linesが空の場合はスキップして安全に処理
