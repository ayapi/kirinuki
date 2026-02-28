# Research & Design Decisions

## Summary
- **Feature**: `video-unavailable-handling`
- **Discovery Scope**: Extension（既存同期システムの拡張）
- **Key Findings**:
  - `download_video()` に既存のDownloadError→AuthenticationRequiredError分類パターンがある。`fetch_video_metadata()` でも同じパターンを適用可能
  - `CookieService` はDB非依存でスタンドアロン動作。Cookie更新時のauth記録リセットはsync側でcookie mtimeを比較して実現
  - SCHEMA_VERSION管理が既存のため、新テーブル追加はマイグレーションで対応

## Research Log

### yt-dlpのDownloadErrorメッセージパターン
- **Context**: メンバー限定動画アクセス失敗時のエラーメッセージを特定する必要がある
- **Sources Consulted**: yt-dlp GitHub Issues #9368, #5796, 既存コード `ytdlp_client.py` L163-166
- **Findings**:
  - メンバー限定: `"Join this channel to get access to members-only content"`
  - 認証要求: `"Sign in"`, `"login"`, `"members-only"`
  - 既存の `download_video()` が同パターンで判定済み（L164-166）
  - `extract_info()` は失敗時に `yt_dlp.DownloadError` を送出するか `None` を返す
- **Implications**: `fetch_video_metadata()` で `download_video()` と同じキーワード判定ロジックを適用する

### CookieServiceのDB非依存性
- **Context**: Req 5.1（cookie set時にauth記録を自動リセット）の実現方法
- **Sources Consulted**: `cookie_service.py`, `cli/cookie.py`, `cli/main.py`
- **Findings**:
  - `CookieService` はDB接続を持たず、CLI側でもDB不使用
  - cookie setコマンドにDB依存を追加するとアーキテクチャが複雑化
  - 代替: `sync_channel()` 実行時にcookie file mtimeと記録日時を比較し、cookieが新しければauth記録を自動クリア
- **Implications**: cookie更新時の即座リセットではなく、次回sync時の遅延リセットとする。ユーザー体験上の差は実質なし

### スキーマバージョン管理
- **Context**: 新テーブル `unavailable_videos` の追加方法
- **Sources Consulted**: `database.py` L18-70, `SCHEMA_VERSION = 1`
- **Findings**:
  - 既存のスキーマバージョン管理は単一バージョン記録のみ（マイグレーション機構なし）
  - `SCHEMA_SQL` に `CREATE TABLE IF NOT EXISTS` パターンで追加すればバージョン1の既存DBでも動作
  - `SCHEMA_VERSION` をインクリメントしてもフォールバック処理がないため、`IF NOT EXISTS` で後方互換を確保する方が安全
- **Implications**: `SCHEMA_SQL` に新テーブル定義を追加し、`IF NOT EXISTS` で既存DBとの互換性を確保

## Design Decisions

### Decision: エラー分類ロジックの配置場所
- **Context**: DownloadError→専用例外の変換をどこで行うか
- **Alternatives Considered**:
  1. `YtdlpClient` 内で変換し専用例外を送出
  2. `SyncService` 側で生の例外をキャッチして分類
- **Selected Approach**: `YtdlpClient` 内（Option 1）
- **Rationale**: `download_video()` で既にこのパターンが存在（L160-174）。一貫性を維持し、infra層で外部ツールのエラーを適切に変換する
- **Trade-offs**: ytdlp_clientがドメイン例外に依存するが、既存パターンと同一

### Decision: Cookie更新時のauth記録リセット方式
- **Context**: `cookie set` 後にauth失敗記録を自動リセットする方法
- **Alternatives Considered**:
  1. cookie setコマンドにDB接続を追加して即座にリセット
  2. sync実行時にcookie mtimeと記録日時を比較して遅延リセット
  3. 新CLIコマンド `sync --retry-auth` を追加
- **Selected Approach**: Option 2（遅延リセット）
- **Rationale**: CookieServiceのDB非依存性を維持。次回syncで自動的にリセットされるためUX上の差は実質なし
- **Trade-offs**: cookie set直後にsync以外の操作をしても記録は残るが、unavailable記録はsyncのみが参照するため影響なし

### Decision: unavailableとskippedの関係
- **Context**: SyncResultのカウントにunavailable記録済みスキップをどう含めるか
- **Alternatives Considered**:
  1. `skipped` に含める
  2. 新フィールド `unavailable_skipped` を追加
- **Selected Approach**: Option 2（新フィールド）
- **Rationale**: 字幕なしスキップ（既存の `skipped`）と意味が異なる。ユーザーが状況を正確に把握するには区別が必要

## Risks & Mitigations
- **Risk**: yt-dlpのエラーメッセージが将来変わる可能性 — キーワード判定をメソッド化し変更時の修正箇所を限定
- **Risk**: cookie mtimeベースのリセットがOSによってはmsec精度不足 — `recorded_at` を秒単位で比較すれば実用上問題なし

## References
- [yt-dlp Membership Restricted Video Issue #9368](https://github.com/yt-dlp/yt-dlp/issues/9368)
- [yt-dlp availability field Issue #12360](https://github.com/yt-dlp/yt-dlp/issues/12360)
- 既存コード: `src/kirinuki/infra/ytdlp_client.py` L160-174（download_video のエラー分類パターン）
