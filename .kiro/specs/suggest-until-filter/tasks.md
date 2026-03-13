# Implementation Plan

- [x] 1. Infra層の拡張
- [x] 1.1 (P) DBスキーマv2マイグレーションとbroadcast_start_at対応メソッド追加
  - `SCHEMA_VERSION` を 1 → 2 に変更し、`SCHEMA_SQL` の videos テーブルに `broadcast_start_at TEXT` カラムを追加する
  - `initialize()` 内でバージョン 1 の DB を検出した場合、`ALTER TABLE videos ADD COLUMN broadcast_start_at TEXT` を実行し、`schema_version` を 2 に更新するマイグレーション処理を追加する
  - `save_video()` に `broadcast_start_at` パラメータを追加し、ISO 8601 形式でDBに保存する
  - `get_latest_videos()` に `until` パラメータを追加し、指定時は `broadcast_start_at` または `published_at` がその日時以前の動画のみ返す。ソート順を `COALESCE(broadcast_start_at, published_at) DESC` に変更する
  - バックフィル用に `get_videos_without_broadcast_start()` と `update_broadcast_start_at()` メソッドを追加する
  - マイグレーション、save_video の broadcast_start_at 保存、get_latest_videos の until フィルタリング、バックフィル用メソッドのユニットテストを作成する
  - _Requirements: 1.3, 1.4, 2.2, 3.1_

- [x] 1.2 (P) YtdlpClient の配信開始日時抽出
  - `VideoMeta` に `broadcast_start_at: datetime | None` フィールドを追加する
  - `fetch_video_metadata()` で yt-dlp の `release_timestamp` を取得し、`datetime.fromtimestamp(ts, tz=timezone.utc)` で変換して `broadcast_start_at` に設定する。取得不可時は None のまま返す
  - `release_timestamp` の抽出とNone時の挙動のユニットテストを作成する
  - _Requirements: 1.1, 1.2_

- [x] 2. Core層の拡張
- [x] 2.1 (P) SyncService の broadcast_start_at 保存対応
  - `_sync_single_video()` 内の `save_video()` 呼び出しに `broadcast_start_at` パラメータを追加する
  - `VideoMeta.broadcast_start_at` が None の場合は `published_at` をフォールバック値として使用する
  - フォールバック適用のユニットテストを作成する
  - _Requirements: 1.1, 1.2_

- [x] 2.2 (P) SuggestService の until フィルタリング対応
  - `SuggestOptions` に `until: datetime | None` フィールドを追加する
  - `_resolve_videos()` で `video_ids` 未指定時に `until` を `get_latest_videos()` に渡すように拡張する。`video_ids` 指定時は `until` を無視する
  - until 適用・未適用・video_ids 優先のユニットテストを作成する
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 3. CLI層の拡張
- [x] 3.1 (P) suggest コマンドに --until オプションを追加
  - `YYYY-MM-DD` と `YYYY-MM-DD HH:MM` の2形式を受け付ける日時パース関数を作成する。日付のみの場合はその日の 23:59:59 として扱う
  - 無効な日時形式が指定された場合、受け付ける形式を案内するエラーメッセージを表示する
  - suggest コマンドに `--until` click オプションを追加し、パースした日時を `SuggestOptions.until` に渡す
  - 日時パースの正常系・異常系、CLIオプション結合のテストを作成する
  - _Requirements: 3.1, 3.3, 3.5_

- [x] 3.2 (P) migrate コマンドグループと backfill-broadcast-start サブコマンドの新規作成
  - CLI メインエントリーに `migrate` サブグループを追加する
  - `backfill-broadcast-start` コマンドを作成し、`broadcast_start_at` が未設定の動画を対象に yt-dlp でメタデータを再取得して配信開始日時を更新する
  - `release_timestamp` が取得不可の動画には `published_at` をフォールバック値として使用する
  - 各動画の処理でエラーが発生しても中断せず次の動画に継続する
  - 処理完了時に更新件数・エラー件数のサマリーを表示する
  - バックフィル処理の一連のフロー（対象選定→取得→更新→サマリー表示）のテストを作成する
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
