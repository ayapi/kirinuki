# Requirements Document

## Introduction
DBに蓄積された動画の一覧を表示するCLIコマンド（`videos`）を追加する。配信日時・タイトル・URLを新しい順に表示し、`--tui`オプションでインタラクティブに動画を選択して既存コマンド（`segments`/`suggest`）へ連携する。

## Requirements

### Requirement 1: 動画一覧の表示
**Objective:** ユーザーとして、蓄積された動画の一覧を新しい順に確認したい。どの動画が登録されているかを素早く把握するため。

#### Acceptance Criteria
1. When `videos`コマンドが実行された場合, the CLIは DB内の全動画を配信日時の新しい順にソートして表示する
2. The CLIは 各動画について配信日時、タイトル、YouTube URLを表示する
3. The CLIは デフォルトで最大20件を表示する
4. When `--count`オプションが指定された場合, the CLIは 指定された件数分の動画を表示する
5. If 動画が1件も登録されていない場合, the CLIは その旨のメッセージを表示する

### Requirement 2: TUIモードでの動画選択
**Objective:** ユーザーとして、一覧から動画をインタラクティブに選択し、その動画に対する操作をすぐに実行したい。動画IDを手入力する手間を省くため。

#### Acceptance Criteria
1. When `--tui`オプションが指定された場合, the CLIは 動画一覧をインタラクティブな選択メニューで表示する
2. When TUIモードで動画が1つ選択された場合, the CLIは 次の操作として`segments`または`suggest`の選択メニューを表示する
3. When `segments`が選択された場合, the CLIは 選択された動画IDで`segments --tui`コマンド相当の処理を実行する
4. When `suggest`が選択された場合, the CLIは 選択された動画IDで`suggest --tui`コマンド相当の処理を実行する
5. The TUIモードでは 動画は1つだけ選択可能とする（マルチセレクトではない）
