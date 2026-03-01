# Requirements Document

## Introduction

`kirinuki sync`コマンドで全動画の字幕取得がスキップされる問題（90件中90件スキップ）の原因究明と対策。
ログ上は全動画で`No subtitle for video [id], skipping`が出力され、新規同期が0件となる。

### 問題の構造

現在のフローでは`YtdlpClient.fetch_subtitle()`が`None`を返すと`SyncService._sync_single_video()`が即座にスキップする。
全動画で`None`が返っているため、yt-dlpの字幕取得オプション・フォーマット指定・自動生成字幕の取り扱いに根本的な問題がある可能性が高い。

### 調査で判明したポイント

- `fetch_subtitle()`は`subtitleslangs: ["ja"]`, `subtitlesformat: "json3"`, `writeautomaticsub: True`で取得を試みる
- `requested_subtitles`辞書に`"ja"`キーが存在しない場合に`None`を返す
- 自動生成字幕（`automatic_captions`）も`writeautomaticsub: True`で取得対象だが、yt-dlpのバージョンやオプション構成によっては正しく`requested_subtitles`に反映されない場合がある
- `subtitlesformat: "json3"`が利用不可能な場合、字幕自体が取得されない可能性がある

## Requirements

### Requirement 1: 字幕取得失敗の原因診断

**Objective:** 開発者として、字幕が取得できない根本原因を特定したい。適切な対策を講じるために正確な診断情報が必要。

#### Acceptance Criteria

1. When `fetch_subtitle()`が`None`を返した場合, the SyncServiceは yt-dlpが返す`subtitles`・`automatic_captions`の有無をDEBUGレベルでログ出力する
2. When 字幕取得を試行する場合, the YtdlpClientは yt-dlpに渡す実際のオプション辞書をDEBUGレベルでログ出力する
3. When yt-dlpが`requested_subtitles`を返さなかった場合, the YtdlpClientは レスポンス内の利用可能な字幕言語・フォーマットの一覧をDEBUGレベルでログ出力する

### Requirement 2: 字幕フォーマットのフォールバック

**Objective:** ユーザーとして、`json3`フォーマットが利用できない場合でも字幕データを取得したい。フォーマット制約で全動画がスキップされるのを防ぐため。

#### Acceptance Criteria

1. When `json3`フォーマットの字幕が取得できなかった場合, the YtdlpClientは 代替フォーマット（`vtt`、`srv3`等）での取得を試行する
2. When 代替フォーマットで字幕が取得できた場合, the YtdlpClientは 取得したフォーマットから`SubtitleData`を正しくパースして返す
3. The YtdlpClientは フォーマットのフォールバック順序を設定可能にする

### Requirement 3: 自動生成字幕の確実な取得

**Objective:** ユーザーとして、手動字幕がない動画でも自動生成字幕（YouTube自動字幕起こし）を確実に取得したい。YouTube Liveアーカイブの大半は自動生成字幕のみであるため。

#### Acceptance Criteria

1. When 動画に手動字幕が存在しない場合, the YtdlpClientは 自動生成字幕を確実にフォールバック取得する
2. When `writeautomaticsub`オプションが有効な場合, the YtdlpClientは 自動生成字幕が`requested_subtitles`に正しく反映されることを検証する
3. If 自動生成字幕も利用できない場合, the YtdlpClientは 「字幕なし」と「取得失敗」を明確に区別してログに記録する

### Requirement 4: 字幕言語の柔軟な指定

**Objective:** ユーザーとして、日本語字幕以外にもフォールバック言語を指定できるようにしたい。日本語字幕が存在しないが英語字幕はある、といったケースに対応するため。

#### Acceptance Criteria

1. The YtdlpClientは 字幕取得の優先言語リスト（デフォルト: `["ja"]`）を設定から読み込む
2. When 第一優先言語の字幕が取得できなかった場合, the YtdlpClientは 次の優先言語で取得を試行する
3. When フォールバック言語で字幕が取得できた場合, the SubtitleDataは 実際に取得した言語コードを正確に記録する

### Requirement 5: syncコマンドのスキップ理由の可視化

**Objective:** ユーザーとして、字幕がスキップされた理由をsyncコマンドの出力で把握したい。「字幕なし」の一言ではなく、原因別の内訳を知りたい。

#### Acceptance Criteria

1. When sync完了時, the CLIは スキップされた動画の理由別内訳（フォーマット不一致・言語なし・字幕データ自体なし等）を表示する
2. When `--verbose`フラグ付きで実行した場合, the CLIは 各スキップ動画のvideo IDとスキップ理由を個別に表示する
3. The SyncResultは スキップ理由のカテゴリ別カウントを保持する
