# Requirements Document

## Introduction

`kirinuki sync` コマンドは、登録済みチャンネルのYouTube Liveアーカイブから字幕・メタデータを差分同期する機能である。
しかし現状の実装では、チャンネルの `/videos` タブから全動画IDを取得しており、ライブ配信アーカイブかどうかの判定を一切行っていない。
その結果、通常のアップロード動画（プレミア公開、ショート、通常動画など）もsync対象に含まれてしまっている。

本仕様では、sync対象をライブ配信アーカイブのみに限定するフィルタリング機能を追加する。

## Requirements

### Requirement 1: ライブ配信アーカイブの識別

**Objective:** ユーザーとして、syncコマンドがライブ配信のアーカイブだけを処理するようにしたい。通常のアップロード動画が紛れ込むことで、不要な字幕データが蓄積されるのを防ぐため。

#### Acceptance Criteria

1. When syncコマンドがチャンネルの動画一覧を取得した後, the sync service shall 各動画のメタデータからライブ配信アーカイブかどうかを判定する
2. The sync service shall yt-dlpの `live_status` フィールドを使用してライブ配信アーカイブを識別する
3. When 動画の `live_status` が `was_live` である場合, the sync service shall その動画をsync対象として処理する
4. When 動画の `live_status` が `was_live` 以外（`not_live`, `is_live`, `is_upcoming`, `post_live` 等）である場合, the sync service shall その動画をsync対象から除外する

### Requirement 2: 非ライブ動画のスキップ処理

**Objective:** ユーザーとして、スキップされた非ライブ動画の数を把握したい。syncの実行結果が正確に報告されるようにするため。

#### Acceptance Criteria

1. When 動画がライブ配信アーカイブではないためスキップされた場合, the sync service shall スキップ理由として「ライブ配信アーカイブではない」を記録する
2. When sync処理が完了した場合, the CLI shall 非ライブ動画としてスキップされた件数を結果サマリーに表示する
3. The sync service shall 非ライブ動画のスキップをログに記録する（動画IDとタイトルを含む）

### Requirement 3: フィルタリングの効率性

**Objective:** ユーザーとして、フィルタリングの追加によってsyncの実行時間が大幅に増加しないようにしたい。日常的に使うコマンドの利便性を保つため。

#### Acceptance Criteria

1. The sync service shall ライブ配信アーカイブの判定を、字幕取得より前の段階で行う（不要な字幕取得を回避）
2. The sync service shall 可能な限り少ないAPI呼び出しでライブ状態を判定する
