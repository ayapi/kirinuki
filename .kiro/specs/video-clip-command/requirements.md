# Requirements Document

## Introduction
YouTube動画の指定区間を切り抜くCLIコマンド `kirinuki clip` を提供する。
ユーザーは動画ID（またはURL）、開始時刻（MM:SS）、終了時刻（MM:SS）、出力先パスを指定して、動画の一部を切り出した動画ファイルを生成できる。
プロダクトのコア機能「オンデマンドクリッピング」を実現するもので、遅延ダウンロード戦略（動画はDL→切り抜き→元動画即時削除）に従う。

## Requirements

### Requirement 1: CLIコマンド引数とオプション
**Objective:** ユーザーとして、動画ID/URLと時間範囲・出力先を直感的に指定して切り抜きを実行したい。スクリプトからも利用しやすいCLIインターフェースを求める。

#### Acceptance Criteria
1. When ユーザーが `kirinuki clip <video> <start> <end> <output>` を実行した場合, the clip command shall 4つの位置引数（動画ID or URL、開始時刻、終了時刻、出力先パス）を受け取り切り抜き処理を開始する
2. When `<video>` 引数にYouTube URLが渡された場合, the clip command shall URLから動画IDを抽出して処理を続行する
3. When `<video>` 引数に11文字の動画IDが直接渡された場合, the clip command shall そのIDをそのまま使用して処理を続行する
4. When `<start>` または `<end>` が `MM:SS` 形式で渡された場合, the clip command shall 秒数に変換して使用する
5. When `<start>` または `<end>` が `HH:MM:SS` 形式で渡された場合, the clip command shall 秒数に変換して使用する

### Requirement 2: 動画ダウンロードと切り抜き処理
**Objective:** ユーザーとして、コマンド一発で「動画DL → 切り出し → クリーンアップ」の一連の処理を実行したい。動画本体をローカルに残さない遅延DL戦略に従う。

#### Acceptance Criteria
1. When 切り抜きコマンドが実行された場合, the clip command shall 一時ディレクトリに動画をダウンロードし、ffmpegで指定区間を切り出し、出力先に保存する
2. When 切り抜き処理が正常に完了した場合, the clip command shall 一時ディレクトリにダウンロードした元動画を即時削除する
3. If 切り抜き処理中にエラーが発生した場合, the clip command shall 一時ディレクトリを確実にクリーンアップする
4. When Cookie認証が必要な動画の場合, the clip command shall 設定済みのCookieファイルを使用してダウンロードを試みる

### Requirement 3: 入力バリデーションとエラーハンドリング
**Objective:** ユーザーとして、不正な入力に対して分かりやすいエラーメッセージを受け取りたい。問題の原因と対処法がすぐに分かるようにする。

#### Acceptance Criteria
1. If 開始時刻が終了時刻以上である場合, the clip command shall エラーメッセージを表示して終了する
2. If 無効なYouTube URL/動画IDが指定された場合, the clip command shall エラーメッセージを表示して終了する
3. If 出力先の親ディレクトリが存在しない場合, the clip command shall エラーメッセージを表示して終了する
4. If ffmpegがシステムにインストールされていない場合, the clip command shall インストール方法を含むエラーメッセージを表示して終了する
5. If 動画のダウンロードに失敗した場合, the clip command shall 失敗原因を含むエラーメッセージを表示して終了する

### Requirement 4: 進捗表示と完了通知
**Objective:** ユーザーとして、処理の進捗状況と結果を把握したい。長時間かかる動画DLの途中経過や、完了時の情報が分かるようにする。

#### Acceptance Criteria
1. When 動画ダウンロードを開始した場合, the clip command shall ダウンロード開始メッセージを表示する
2. When ffmpegによる切り出しを開始した場合, the clip command shall 切り出し処理中のメッセージを表示する
3. When 切り抜きが正常に完了した場合, the clip command shall 出力ファイルパスと切り抜き時間範囲を表示する
