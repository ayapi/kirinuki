# Requirements Document

## Introduction

`kirinuki sync` コマンドは `extract_flat=True` でチャンネルの全動画IDを取得し、個別にメタデータ・字幕を同期する。
しかし、flat extractionはメンバー限定動画のIDも含めて返すため、Cookie期限切れの状態でこれらの動画にアクセスすると「Video unavailable」（yt-dlpでは "Join this channel to get access to members-only content" 等）が発生する。

現状の問題点:
- `ytdlp_client.fetch_video_metadata()` 内の `assert info is not None` が不親切なAssertionErrorになる
- メンバー限定のauth失敗と、動画が本当に削除/非公開になったケースの区別ができない
- Cookie期限切れが原因の場合、ユーザーに更新を促す案内がない
- 同じunavailable動画が毎回再試行される

本仕様では、メンバー限定動画のauth失敗を正しく検出・分類し、ユーザーに適切な対処を案内し、無駄な再試行を防止する。

## Requirements

### Requirement 1: yt-dlpエラーの分類と専用例外

**Objective:** ユーザーとして、sync失敗の原因が「Cookie期限切れによるメンバー限定動画へのアクセス失敗」なのか「動画自体の削除・非公開」なのかを区別したい。これにより適切な対処（Cookie更新 or 無視）を判断できる。

#### Acceptance Criteria

1. When yt-dlpが動画メタデータ取得時にDownloadErrorを送出した場合, the kirinuki shall エラーメッセージの内容（"Join this channel", "Sign in", "members-only" 等）を解析してメンバー限定auth失敗かどうかを判定する
2. When メンバー限定auth失敗と判定された場合, the kirinuki shall 専用の例外（`AuthenticationRequiredError`）でエラーを通知する
3. When yt-dlpが動画メタデータ取得時にNoneを返した場合, the kirinuki shall `assert` ではなく `VideoUnavailableError` を送出する
4. When 上記いずれにも該当しないDownloadErrorの場合, the kirinuki shall `VideoUnavailableError` でエラーを通知する

### Requirement 2: メンバー限定auth失敗時のユーザー案内

**Objective:** ユーザーとして、Cookie期限切れが原因でメンバー限定動画の同期に失敗した場合、Cookie更新の方法を案内されたい。これにより問題を速やかに解消できる。

#### Acceptance Criteria

1. When 同期中にメンバー限定auth失敗が1件以上発生した場合, the kirinuki shall 同期完了時にCookie更新を促すメッセージ（`kirinuki cookie set` の案内）を表示する
2. The kirinuki shall 同期結果において、メンバー限定auth失敗の件数を他のエラーと分けて表示する

### Requirement 3: 同期処理の継続性

**Objective:** ユーザーとして、一部の動画がunavailableでも残りの動画の同期が正常に完了してほしい。

#### Acceptance Criteria

1. When 個別動画の同期でVideoUnavailableErrorまたはAuthenticationRequiredErrorが発生した場合, the kirinuki shall 当該動画をスキップして次の動画の同期を継続する
2. When 同期処理が完了した場合, the kirinuki shall エラーとなった動画のID・理由の一覧を表示する

### Requirement 4: unavailable動画の記録と再同期スキップ

**Objective:** ユーザーとして、unavailableと判定済みの動画が毎回再試行されないようにしたい。これにより同期の実行時間を短縮しAPIリクエストを削減できる。

#### Acceptance Criteria

1. When 動画がVideoUnavailableError（恒久的な問題）と判定された場合, the kirinuki shall その動画IDと理由をデータベースに記録する
2. When 動画がAuthenticationRequiredError（Cookie更新で解決可能）と判定された場合, the kirinuki shall その動画IDと理由をデータベースに記録する
3. When 次回の同期実行時, the kirinuki shall 記録済みのunavailable動画IDをスキップする
4. The kirinuki shall スキップされた記録済みunavailable動画の件数を同期結果サマリーに含める

### Requirement 5: unavailable記録のリセット

**Objective:** ユーザーとして、Cookie更新後にメンバー限定動画の再同期を試みたい。また、誤ってunavailableと記録された動画を回復したい。

#### Acceptance Criteria

1. When ユーザーが `kirinuki cookie set` でCookieを更新した場合, the kirinuki shall auth失敗（AuthenticationRequiredError）で記録された動画のunavailable記録を自動的にリセットする
2. When ユーザーが明示的にunavailable記録のリセットを要求した場合, the kirinuki shall 指定されたチャンネルまたは全体のunavailable記録を削除する
