# Implementation Plan

- [x] 1. ドメインモデルと例外の基盤整備
- [x] 1.1 (P) VideoUnavailableError例外の追加とSyncResultの拡張
  - `VideoUnavailableError` 例外クラスを追加する。動画IDと理由メッセージを保持し、エラー内容から動画を特定できるようにする
  - `SyncResult` に `auth_errors`（メンバー限定auth失敗件数）と `unavailable_skipped`（記録済みunavailableスキップ件数）フィールドを追加する
  - 既存の `SyncResult` 集計ロジック（`sync_all` でのフィールド合算）に新フィールドを反映する
  - _Requirements: 1.3, 1.4, 2.2, 4.4_

- [x] 2. Databaseのunavailable_videos対応
- [x] 2.1 (P) unavailable_videosテーブルとCRUDメソッドの実装
  - `unavailable_videos` テーブルをスキーマに追加する。動画ID・チャンネルID・エラー種別（`auth_required` / `unavailable`）・理由・記録日時を格納する
  - unavailable動画を記録するメソッドを実装する。同一動画の再記録はUPSERT（上書き更新）とする
  - チャンネル別にunavailable動画IDのセットを取得するメソッドを実装する
  - auth失敗記録の最古日時を取得するメソッドを実装する（cookie mtime比較用）
  - エラー種別指定での削除、チャンネル指定または全件の削除メソッドを実装する
  - 上記CRUD操作のユニットテストを記述する
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2_

- [x] 3. YtdlpClientのエラー分類
- [x] 3.1 auth判定ヘルパーの抽出とfetch_video_metadataのエラーハンドリング
  - `download_video()` にある認証エラー判定ロジック（"Sign in", "login", "members-only" キーワード）を共通メソッド `_is_auth_error()` に抽出し、`download_video()` をリファクタリングする
  - 判定キーワードに `"Join this channel"` を追加する（メンバー限定動画の主要なエラーメッセージ）
  - `fetch_video_metadata()` の `assert info is not None` を削除し、info=None時は `VideoUnavailableError` を送出するよう変更する
  - `fetch_video_metadata()` で `yt_dlp.DownloadError` をキャッチし、`_is_auth_error()` でauth失敗判定する。auth失敗なら `AuthenticationRequiredError`、それ以外なら `VideoUnavailableError` を送出する
  - `_is_auth_error()` のキーワード判定テスト、`fetch_video_metadata()` のDownloadError→専用例外変換テスト、info=None→VideoUnavailableErrorテストを記述する
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 4. SyncServiceの同期ロジック更新
- [x] 4.1 unavailableフィルタリング・記録・cookie自動リセットの統合
  - `sync_channel()` の冒頭でcookieファイルのmtimeとauth失敗記録の最古日時を比較し、cookieが新しければauth失敗記録を自動クリアする処理を追加する
  - new_ids算出時にDBの既存動画IDに加えてunavailable記録済みIDも除外し、スキップ件数を `unavailable_skipped` に計上する
  - `_sync_single_video()` で `AuthenticationRequiredError` と `VideoUnavailableError` を個別にキャッチし、DB記録して `auth_errors` またはエラー一覧に計上する。他の動画の同期は継続する
  - `SyncService` のコンストラクタにcookieファイルパスへのアクセス手段を追加する（`AppConfig` 経由）
  - auth失敗DB記録・unavailableスキップ・cookie自動リセット・混在ケースのユニットテストを記述する
  - _Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 5.1_

- [x] 5. CLI出力とリセットコマンドの実装
- [x] 5.1 syncコマンドのエラー表示改善とCookie案内
  - sync結果表示にauth失敗件数とunavailableスキップ件数を追加する
  - auth失敗が1件以上ある場合、Cookie更新を促すメッセージ（`kirinuki cookie set` の案内）を表示する
  - 既存のエラー一覧表示は維持する
  - _Requirements: 2.1, 2.2, 3.2, 4.4_

- [x] 5.2 unavailable記録リセットのサブコマンド追加
  - unavailable記録をリセットするCLIサブコマンドを追加する。チャンネルID指定で特定チャンネルのみ、または全チャンネルのリセットに対応する
  - 削除件数をユーザーに表示する
  - _Requirements: 5.2_
