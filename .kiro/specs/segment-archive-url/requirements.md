# Requirements Document

## Introduction

CLIコマンド `search`・`segments`・`suggest` の出力結果すべてに、YouTube Liveアーカイブの該当区間へ直接ジャンプできるURL（`&t=` パラメータ付き）を一貫して表示する。
これにより、ユーザーは検索・一覧・推薦のどの操作からでもワンクリックで動画内容を確認できる。

### 現状分析

| コマンド | URL表示 | 備考 |
|----------|---------|------|
| `search` | あり | `SearchResult.youtube_url` として既に表示 |
| `segments` | **なし** | 時間範囲と要約のみ表示。`video_id` は引数として渡されているがURLは生成されていない |
| `suggest` | あり | `RecommendationFormatter.build_youtube_url()` で生成・表示済み |

主な実装対象は `segments` コマンドへのURL追加と、3コマンド間でのURL生成ロジックの統一化である。

## Requirements

### Requirement 1: segments コマンドへのアーカイブURL表示追加

**Objective:** ユーザーとして、`segments` コマンドの出力にYouTube LiveアーカイブのURLを表示してほしい。それにより、セグメント一覧から直接その区間の動画を視聴できるようにしたい。

#### Acceptance Criteria

1. When ユーザーが `segments <video_id>` コマンドを実行した場合, the CLI shall 各セグメントの表示に `https://www.youtube.com/watch?v=<video_id>&t=<start_seconds>` 形式のURLを含める
2. The CLI shall `&t=` パラメータにセグメントの開始時刻（秒単位、小数点以下切り捨て）を設定する
3. When セグメントが0件の場合, the CLI shall 既存の「セグメントはありません」メッセージのみを表示し、URLは表示しない

### Requirement 2: 全コマンド共通のURL生成ロジック統一

**Objective:** 開発者として、YouTube URL生成ロジックを共通化したい。それにより、URL形式の変更時に一箇所の修正で済むようにしたい。

#### Acceptance Criteria

1. The CLI shall `search`・`segments`・`suggest` の3コマンドで同一のURL生成関数を使用してYouTube URLを生成する
2. The URL生成関数 shall `video_id` と開始時刻（ミリ秒）を受け取り、`https://www.youtube.com/watch?v=<video_id>&t=<start_seconds>` 形式の文字列を返す
3. The URL生成関数 shall 開始時刻のミリ秒を秒に変換する際、小数点以下を切り捨てる（整数秒）

### Requirement 3: 既存コマンド（search・suggest）のURL表示維持

**Objective:** ユーザーとして、既に動作している `search` および `suggest` コマンドのURL表示が、今回の変更で壊れないことを保証したい。

#### Acceptance Criteria

1. When ユーザーが `search <query>` コマンドを実行した場合, the CLI shall 従来通り各検索結果にタイムスタンプ付きYouTube URLを表示する
2. When ユーザーが `suggest <channel>` コマンドをテキスト出力で実行した場合, the CLI shall 従来通り各推薦候補に `URL:` 行としてタイムスタンプ付きURLを表示する
3. When ユーザーが `suggest <channel> --json` コマンドを実行した場合, the CLI shall 従来通り各推薦候補のJSONに `youtube_url` フィールドを含める
