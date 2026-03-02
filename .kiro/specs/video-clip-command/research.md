# Research & Design Decisions

## Summary
- **Feature**: `video-clip-command`
- **Discovery Scope**: Extension（既存コンポーネントの結合）
- **Key Findings**:
  - 切り抜きに必要な基盤（モデル、ユーティリティ、インフラ層）は既に実装済み
  - CLIコマンドとオーケストレーション層（サービス）の追加のみが必要
  - 既存のエラー型が全ての異常系をカバーしている

## Research Log

### 既存コンポーネントの充足度分析
- **Context**: 新規に必要なコードの範囲を特定するため、既存実装を調査
- **Sources Consulted**: `models/clip.py`, `core/clip_utils.py`, `infra/ffmpeg.py`, `infra/ytdlp_client.py`, `core/errors.py`
- **Findings**:
  - `ClipRequest` / `ClipResult` モデル — 時間範囲バリデーション、出力フォーマット検証を含む
  - `clip_utils.py` — `extract_video_id()`, `parse_time_str()`, `seconds_to_ffmpeg_time()`, `format_default_filename()` が利用可能
  - `FfmpegClientImpl` — `clip()` メソッドで区間切り出し済み、`check_available()` で存在確認
  - `YtdlpClient.download_video()` — Cookie認証対応のDL機能
  - `errors.py` — `InvalidURLError`, `TimeRangeError`, `FfmpegNotFoundError`, `VideoDownloadError`, `ClipError`, `AuthenticationRequiredError` が定義済み
- **Implications**: 新規作成は `core/clip_service.py`（オーケストレーション）と `cli/clip.py`（CLIコマンド）の2ファイルのみ

### 動画ID判定ロジック
- **Context**: `<video>` 引数がURLか動画IDかを判定する方法の検討
- **Sources Consulted**: `core/clip_utils.py` の `extract_video_id()`、yt-dlpのURL正規表現パターン
- **Findings**:
  - `extract_video_id()` はURL形式のみ対応（`youtube.com/watch?v=`, `youtu.be/`, `youtube.com/live/`）
  - 11文字の動画IDが直接渡された場合のハンドリングは未実装
  - yt-dlpの動画ID正規表現: `^[a-zA-Z0-9_-]{11}$` が `ytdlp_client.py` に定義済み
- **Implications**: `resolve_video_id()` 関数を新設し、URL/ID両方を受け付けるロジックが必要

## Design Decisions

### Decision: オーケストレーション層の配置
- **Context**: DL→切り出し→クリーンアップの一連処理をどこに置くか
- **Alternatives Considered**:
  1. CLI層に直接実装 — シンプルだが薄いCLI層の原則に反する
  2. `core/clip_service.py` に新規サービス — 既存パターンに合致
- **Selected Approach**: `core/clip_service.py` に `ClipService` を新設
- **Rationale**: structure.mdの「CLI層は薄く」「コア層は外部非依存」原則に従う。テスト時にインフラ層をモック差し替え可能
- **Trade-offs**: ファイル数が増えるが、責務分離とテスタビリティを優先

### Decision: 一時ディレクトリ管理
- **Context**: ダウンロードした元動画の一時保存と確実なクリーンアップ
- **Alternatives Considered**:
  1. `tempfile.TemporaryDirectory()` コンテキストマネージャ — Pythonの標準パターン
  2. `ClipRequest.temp_dir` フィールドの利用 — カスタムパス指定可能
- **Selected Approach**: `tempfile.TemporaryDirectory()` をデフォルトとし、`ClipRequest.temp_dir` が指定されていればそちらを使用
- **Rationale**: コンテキストマネージャによりエラー時も確実にクリーンアップされる
- **Follow-up**: 例外発生時のクリーンアップをテストで検証

## Risks & Mitigations
- 長時間動画のDLで時間がかかる — 進捗メッセージで状況を通知（Req 4）
- Cookie期限切れによるDL失敗 — `AuthenticationRequiredError` で適切なガイダンスを表示
- ffmpeg未インストール — 処理開始前に `check_available()` で事前チェック

## References
- yt-dlp公式ドキュメント — https://github.com/yt-dlp/yt-dlp
- ffmpegドキュメント — https://ffmpeg.org/documentation.html
