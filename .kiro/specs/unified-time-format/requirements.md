# Requirements Document

## Introduction
search、suggest、segmentsコマンドの時間範囲表示を、clipコマンドの引数にそのままコピペできる `MM:SS-MM:SS` 形式に統一する。
現状、コマンドによって区切り文字（` - `、`〜`）やフォーマットが異なり、clipコマンドに渡す際に手動で整形する必要がある。

### 現状の課題
- **searchコマンド**: `23:45 - 25:30`（スペース付きハイフン区切り）
- **segmentsコマンド**: `23:45 - 25:30`（スペース付きハイフン区切り）
- **suggestコマンド**: `23:45 〜 25:30`（波ダッシュ区切り）
- **clipコマンド引数**: `23:45-25:30`（スペースなしハイフン区切り）を期待

clipコマンドに渡すには区切り文字とスペースの手動修正が必要であり、UXを損ねている。

## Requirements

### Requirement 1: 時間範囲表示フォーマットの統一
**Objective:** ユーザーとして、search / suggest / segments の出力時間範囲を、clip コマンドにそのままコピペしたい。それにより手動の整形作業を省きたい。

#### Acceptance Criteria
1. When searchコマンドが検索結果を表示するとき, the CLIは時間範囲を `MM:SS-MM:SS` 形式（スペースなしハイフン区切り）で出力しなければならない
2. When segmentsコマンドがセグメント一覧を表示するとき, the CLIは時間範囲を `MM:SS-MM:SS` 形式（スペースなしハイフン区切り）で出力しなければならない
3. When suggestコマンドが推薦結果を表示するとき, the CLIは時間範囲を `MM:SS-MM:SS` 形式（スペースなしハイフン区切り）で出力しなければならない
4. While 動画の長さが1時間以上のとき, the CLIは `H:MM:SS-H:MM:SS` 形式で出力しなければならない（clipコマンドのパーサーが対応済み）
5. The CLIが出力する時間範囲文字列は、clipコマンドの `time_ranges` 引数にそのまま渡して正しくパースされなければならない

### Requirement 2: clipコマンド出力の整合性
**Objective:** ユーザーとして、clipコマンドの完了表示でも同じ時間フォーマットを使いたい。それにより全コマンドで一貫した表示体験を得たい。

#### Acceptance Criteria
1. When clipコマンドが処理結果のサマリーを表示するとき, the CLIは時間範囲を `MM:SS-MM:SS` 形式（スペースなしハイフン区切り）で出力しなければならない

### Requirement 3: 既存のformat_time関数の出力互換性
**Objective:** 開発者として、format_time関数の基本出力（秒→時刻文字列変換）は変更せず、時間範囲の結合フォーマットのみを修正したい。それにより影響範囲を最小化したい。

#### Acceptance Criteria
1. The `format_time` 関数は、単一時刻のフォーマット（`M:SS` / `H:MM:SS`）を変更してはならない
2. The 時間範囲の結合（start-end）は、各コマンドの表示箇所またはフォーマッタで一貫した区切り文字（`-`、スペースなし）を使用しなければならない
