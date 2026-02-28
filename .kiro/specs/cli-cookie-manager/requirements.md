# Requirements Document

## Introduction
YouTube Liveアーカイブのメンバー限定動画にアクセスするためにはcookies.txtによる認証が必要だが、cookiesは頻繁に更新が必要になる。現状ではcookies.txtのパスを環境変数で指定する必要があり、ファイルの管理が煩雑である。本機能では、CLI上でcookiesの内容を直接ペーストするだけで内部の固定パスに保存・更新できるようにし、ユーザーの運用負荷を軽減する。

## Requirements

### Requirement 1: CLIからのCookie入力・更新
**Objective:** ユーザーとして、CLI上でcookiesの内容をペーストするだけでcookies.txtを更新したい。これにより、ブラウザからエクスポートしたcookiesを素早く反映できる。

#### Acceptance Criteria
1. When ユーザーがcookie更新コマンドを実行した時, the CLIツール shall cookiesの内容を標準入力から受け付けるインタラクティブモードに入る
2. When ユーザーがcookiesの内容をペーストして入力を確定した時, the CLIツール shall 受け取った内容を内部の固定パスにcookies.txtとして保存する
3. When 保存が正常に完了した時, the CLIツール shall 保存成功のメッセージを表示する
4. If ペーストされた内容が空である場合, the CLIツール shall エラーメッセージを表示し、保存を行わない

### Requirement 2: 固定パスでの内部Cookie管理
**Objective:** ユーザーとして、cookies.txtの保存場所を意識せずに利用したい。これにより、環境変数の設定やパス指定の手間がなくなる。

#### Acceptance Criteria
1. The CLIツール shall cookies.txtをアプリケーション内部の固定パスに保存する（ユーザーによるパス指定は不要）
2. The CLIツール shall 環境変数によるcookies.txtパスの指定を必要としない
3. When yt-dlpを使用した動画・字幕取得を実行する時, the CLIツール shall 内部の固定パスに保存されたcookies.txtを自動的に使用する

### Requirement 3: Cookie状態の確認
**Objective:** ユーザーとして、現在cookiesが設定済みかどうかを確認したい。これにより、認証エラーの原因を素早く特定できる。

#### Acceptance Criteria
1. When ユーザーがcookie状態確認コマンドを実行した時, the CLIツール shall cookies.txtが存在するかどうかを表示する
2. When cookies.txtが存在する場合, the CLIツール shall ファイルの最終更新日時を表示する
3. If cookies.txtが存在しない状態でメンバー限定動画へのアクセスを試みた場合, the CLIツール shall cookiesが未設定である旨の警告メッセージを表示する

### Requirement 4: Cookieの削除
**Objective:** ユーザーとして、保存済みのcookiesを削除したい。これにより、不要になった認証情報を安全に除去できる。

#### Acceptance Criteria
1. When ユーザーがcookie削除コマンドを実行した時, the CLIツール shall 確認プロンプトを表示する
2. When ユーザーが削除を確認した時, the CLIツール shall 内部の固定パスからcookies.txtを削除する
3. When 削除が正常に完了した時, the CLIツール shall 削除成功のメッセージを表示する
