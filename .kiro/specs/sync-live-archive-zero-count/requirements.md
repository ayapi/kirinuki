# Requirements Document

## Introduction

`kirinuki sync`コマンドで、ライブ配信アーカイブが大量にあるはずのチャンネルで「取得済み 0件 / 新規 0件 / スキップ 0件」になる問題の原因究明と対処。

現在の `list_channel_video_ids()` はチャンネルURLに `/videos` を付加して動画一覧を取得しているが、YouTubeはライブ配信アーカイブを `/streams` タブに分離しているため、ライブアーカイブが `/videos` タブに含まれず0件になるケースがある。syncコマンドの目的はライブ配信アーカイブの字幕取得であるため、`/streams` タブも取得対象に含める必要がある。

## Requirements

### Requirement 1: ストリームタブからの動画ID取得

**Objective:** ユーザーとして、ライブ配信アーカイブがYouTubeの `/streams` タブにある場合でも、syncコマンドで正しく検出・取得できるようにしたい。これにより、ライブ配信を主体とするチャンネルのアーカイブを漏れなく蓄積できる。

#### Acceptance Criteria

1. When syncコマンドが実行された場合, the SyncService shall チャンネルの `/videos` タブと `/streams` タブの両方から動画IDを取得する
2. When `/videos` と `/streams` の両方に同じ動画IDが存在する場合, the SyncService shall 重複を排除して1回だけ処理する
3. If `/streams` タブからの取得が失敗した場合, the SyncService shall エラーをログに記録し、`/videos` タブの結果のみで同期を継続する
4. If `/videos` タブからの取得が失敗した場合, the SyncService shall エラーをログに記録し、`/streams` タブの結果のみで同期を継続する

### Requirement 2: 取得件数の可観測性

**Objective:** ユーザーとして、syncコマンド実行時にどのタブから何件の動画が検出されたかを把握したい。これにより、0件問題の原因特定が容易になる。

#### Acceptance Criteria

1. When syncコマンドが完了した場合, the SyncService shall 取得済み・新規・スキップの件数サマリーを従来通り表示する
2. When `--verbose` または適切なログレベルが設定されている場合, the SyncService shall タブごと（videos/streams）の検出件数をログ出力する

### Requirement 3: 既存動作の後方互換性

**Objective:** 開発者として、この変更により既存のsync処理が壊れないことを保証したい。

#### Acceptance Criteria

1. The SyncService shall ライブ配信アーカイブ以外の通常動画（`live_status != "was_live"`）を従来通りスキップする
2. The SyncService shall 既にDB保存済みの動画を `already_synced` としてカウントし、再処理しない
3. The SyncService shall unavailable記録済みの動画を除外する既存動作を維持する
4. When チャンネルに `/streams` タブが存在しない場合, the SyncService shall エラーなく `/videos` タブのみで同期を完了する
