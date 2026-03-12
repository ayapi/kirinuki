# Requirements Document

## Introduction
YouTube Liveの配信アーカイブでは、動画の公開日（`upload_date`）と実際の配信開始日時（`release_timestamp`）が異なる場合がある。現在のDBスキーマは `published_at`（公開日）のみを保持しており、配信開始日時は保存されていない。本仕様では、配信開始日時を正しく取得・保存し、`suggest` コマンドに `--until` フィルターを追加して配信開始日時で絞り込めるようにする。また、既にDBに保存済みの動画に対しては、配信開始日時を一括取得して更新するマイグレーションスクリプトを提供する。

## Requirements

### Requirement 1: 配信開始日時の取得と保存
**Objective:** As a ユーザー, I want 動画の配信開始日時がDBに正しく保存される, so that 配信開始日時を基準にした正確な絞り込みができる

#### Acceptance Criteria
1. When 動画メタデータを取得する際, the sync コマンド shall yt-dlpから配信開始日時（`release_timestamp` または同等のフィールド）を取得してDBに保存する
2. When 配信開始日時が取得できない動画の場合, the sync コマンド shall `published_at`（公開日）をフォールバック値として配信開始日時カラムに保存する
3. The videos テーブル shall 配信開始日時を格納するカラムを持つ
4. When DBスキーマが旧バージョンの場合, the アプリケーション shall 配信開始日時カラムを追加するスキーママイグレーションを実行する

### Requirement 2: 既存動画の配信開始日時バックフィル
**Objective:** As a ユーザー, I want 既にDBに保存済みの動画の配信開始日時を一括で取得・更新したい, so that 既存データに対しても `--until` フィルターが正しく機能する

#### Acceptance Criteria
1. The CLIツール shall 既存動画の配信開始日時を一括取得・更新するマイグレーションコマンドまたはサブコマンドを提供する
2. When マイグレーションを実行する際, the マイグレーション処理 shall 配信開始日時が未設定の動画のみを対象にyt-dlpからメタデータを再取得して更新する
3. When yt-dlpから配信開始日時が取得できない動画の場合, the マイグレーション処理 shall `published_at` の値をフォールバックとして使用し、スキップせずに更新する
4. When マイグレーションが正常に完了した場合, the マイグレーション処理 shall 処理件数（更新済み・スキップ・エラー）をサマリーとして表示する
5. The マイグレーション処理 shall 途中でエラーが発生しても残りの動画の処理を継続する

### Requirement 3: suggest コマンドの --until フィルター
**Objective:** As a ユーザー, I want `suggest` コマンドで `--until` オプションを指定して配信開始日時で絞り込みたい, so that 特定の日時以前の配信のみを対象に切り抜き候補の推薦を受けられる

#### Acceptance Criteria
1. When `--until` オプションに日時を指定して `suggest` コマンドを実行した場合, the suggest コマンド shall 配信開始日時がその日時以前の動画のみを対象に推薦を行う
2. When `--until` オプションが省略された場合, the suggest コマンド shall 従来通り配信開始日時による絞り込みを行わない（全動画を対象とする）
3. The `--until` オプション shall 日付（`YYYY-MM-DD`）および日時（`YYYY-MM-DD HH:MM`等）の入力形式を受け付ける
4. When `--until` と `--video-id` が同時に指定された場合, the suggest コマンド shall `--video-id` を優先し `--until` による絞り込みを無視する
5. If 無効な日時形式が `--until` に指定された場合, the suggest コマンド shall エラーメッセージとともに受け付ける形式を表示する
