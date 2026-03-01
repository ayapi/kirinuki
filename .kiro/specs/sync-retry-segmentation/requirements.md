# Requirements Document

## Introduction

`kirinuki sync` でセグメンテーションに失敗した動画（APIクレジット不足等）は、動画・字幕データがDBに保存済みであるにもかかわらず、次回sync時に `already_synced` としてスキップされ、セグメンテーションが再試行されない。

現在の実装では、動画・字幕のDB保存後にセグメンテーションを実行し、失敗してもログ出力のみで処理を続行する。次回sync時には `get_existing_video_ids()` で既存と判定されるため、セグメンテーション未完了の動画が永久に放置される。

字幕データはDB保存済みなので、セグメンテーションの再試行にはYouTubeからの再取得は不要。DB内の字幕データを使って再試行できる。

## Requirements

### Requirement 1: セグメンテーション未完了動画の再試行

**Objective:** ユーザーとして、セグメンテーションに失敗した動画が次回の `kirinuki sync` で自動的に再試行されるようにしたい。これにより、一時的なAPIエラー（クレジット不足等）が解消された後にsyncを再実行するだけでセグメンテーションが完了する。

#### Acceptance Criteria

1. When syncが実行された場合, the SyncService shall DB保存済みでセグメンテーション未完了の動画を検出し、DB内の字幕データを使ってセグメンテーションを再試行する
2. When セグメンテーション再試行が成功した場合, the SyncService shall その動画を再試行成功としてカウントする
3. If セグメンテーション再試行が失敗した場合, the SyncService shall エラーをログに記録し、次回syncでの再試行対象として残す

### Requirement 2: 再試行結果の可観測性

**Objective:** ユーザーとして、sync完了時にセグメンテーション再試行の結果を把握したい。

#### Acceptance Criteria

1. When syncが完了した場合, the SyncService shall セグメンテーション再試行の件数（成功・失敗）をサマリーに含める
2. The SyncService shall 従来の取得済み・新規・スキップのサマリー表示を維持する

### Requirement 3: 既存動作の後方互換性

**Objective:** 開発者として、この変更が既存のsync処理に影響しないことを保証したい。

#### Acceptance Criteria

1. The SyncService shall 新規動画の同期処理（メタデータ・字幕取得・セグメンテーション）を従来通り実行する
2. The SyncService shall セグメンテーション完了済みの動画を再処理しない
3. The SyncService shall セグメンテーション再試行時にYouTubeへのAPI呼び出しを行わない（DB内の字幕データのみを使用する）
