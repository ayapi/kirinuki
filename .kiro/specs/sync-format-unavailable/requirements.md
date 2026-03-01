# Requirements Document

## Introduction

`sync`コマンド実行時に "Requested format is not available" エラーが発生し、本来取得可能な字幕・メタデータまで取得できなくなる問題への対処。

### 背景・原因分析

`sync`は字幕とメタデータのみを取得する操作であり、動画本体のダウンロードは行わない（`skip_download=True`）。
しかし、yt-dlpは`extract_info()`呼び出し時に内部的にフォーマット選択処理を実行する。
`YtdlpClient._base_opts()`には`format`オプションも`ignore_no_formats_error`オプションも設定されていないため、yt-dlpのデフォルトフォーマットスペック（`bestvideo+bestaudio/best`）が適用される。
特定の動画（制限付きアーカイブ、一部フォーマットのみ提供される動画など）でこのデフォルトスペックにマッチするフォーマットが存在しない場合、`DownloadError`が発生する。

現状このエラーは`VideoUnavailableError`として捕捉され「利用不可」としてDBに記録されるが、字幕やメタデータ自体は取得可能な場合があるため、データ欠損が生じている。

### 影響範囲

- `YtdlpClient.fetch_video_metadata()` — メタデータ取得
- `YtdlpClient.fetch_subtitle()` — 字幕取得
- `SyncService._sync_single_video()` — 同期処理のエラーハンドリング

## Requirements

### Requirement 1: 字幕・メタデータ取得時のフォーマットエラー抑制

**Objective:** ユーザーとして、動画フォーマットが利用不可でも字幕・メタデータは正常に取得できるようにしたい。同期の網羅性を確保するため。

#### Acceptance Criteria

1. When `fetch_video_metadata()`が呼び出される, the YtdlpClient shall yt-dlpのフォーマット選択エラーを無視してメタデータ抽出を続行する
2. When `fetch_subtitle()`が呼び出される, the YtdlpClient shall yt-dlpのフォーマット選択エラーを無視して字幕抽出を続行する
3. While `skip_download=True`が設定されている, the YtdlpClient shall 動画フォーマットの可用性に依存せず情報抽出を完了する

### Requirement 2: エラー分類の精緻化

**Objective:** ユーザーとして、「フォーマット不可」と「動画利用不可」を区別できるようにしたい。問題の切り分けを正確に行うため。

#### Acceptance Criteria

1. If フォーマット不可エラーが発生しても字幕・メタデータが取得できた場合, the SyncService shall 当該動画を正常同期として扱い、unavailableとして記録しない
2. If フォーマット不可エラーにより字幕もメタデータも取得できない場合, the SyncService shall 適切なエラー理由とともにunavailableとして記録する

### Requirement 3: 動画ダウンロード（clip）への非影響

**Objective:** 開発者として、字幕取得の修正が動画ダウンロード機能に影響しないことを保証したい。既存機能の安定性を維持するため。

#### Acceptance Criteria

1. When `download_video()`が呼び出される, the YtdlpClient shall 既存のフォーマット指定（`bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]`）を維持し、フォーマットエラーを正常にraiseする
2. The YtdlpClient shall `_base_opts()`の変更が`download_video()`のフォーマット選択動作に影響しないことを保証する
