# Implementation Plan

- [ ] 1. CookieService コア実装
- [ ] 1.1 CookieService と CookieStatus の実装
  - cookies.txt のファイル操作を担当するサービスクラスを作成する
  - CookieStatus データクラス（存在有無、最終更新日時）を定義する
  - `save()`: cookies内容を受け取り、`~/.kirinuki/cookies.txt` に保存する。ディレクトリが存在しない場合は自動作成し、ファイルパーミッションを600に設定する
  - `save()`: 内容が空または空白のみの場合は ValueError を発生させる
  - `status()`: cookies.txt の存在有無と最終更新日時を返す
  - `delete()`: cookies.txt を削除する。ファイルが存在しない場合は FileNotFoundError を発生させる
  - cookie保存先パスはモジュール定数として `~/.kirinuki/cookies.txt` に固定する
  - _Requirements: 1.2, 1.4, 2.1, 3.1, 3.2, 4.2_

- [ ] 1.2 CookieService のユニットテスト
  - save: 正常保存でファイルが作成され内容が一致することを検証
  - save: 空文字列で ValueError が発生することを検証
  - save: ディレクトリが存在しない場合に自動作成されることを検証
  - status: ファイル存在時に exists=True と更新日時が返ることを検証
  - status: ファイル不在時に exists=False と updated_at=None が返ることを検証
  - delete: 正常削除でファイルが消えることを検証
  - delete: ファイル不在時に FileNotFoundError が発生することを検証
  - テスト用の一時ディレクトリを使用し、ホームディレクトリの実ファイルに影響しないようにする
  - _Requirements: 1.2, 1.4, 2.1, 3.1, 3.2, 4.2_

- [ ] 2. (P) AppConfig モデル更新
  - `cookie_file_path` のデフォルト値を `~/.kirinuki/cookies.txt` に変更する
  - 型を `Path | None` から `Path` に変更する
  - 環境変数 `KIRINUKI_COOKIE_FILE_PATH` によるオーバーライドを廃止する
  - `.env.example` から `KIRINUKI_COOKIE_FILE_PATH` の項目を削除する
  - `YtdlpClient._base_opts()` で cookie_file_path が常に値を持つため、ファイルの存在チェックに変更する
  - 既存テストで cookie_file_path を使用している箇所を更新する
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. Cookie CLI コマンド実装（タスク1に依存）
- [ ] 3.1 cookie コマンドグループの作成と登録
  - `cookie` Click コマンドグループを作成する
  - `cookie set`: 標準入力からcookies内容を読み取り、CookieService.save() で保存する。インタラクティブモード時はEOF入力方法（Ctrl+D / Ctrl+Z）の案内を表示する。保存成功時にメッセージを表示する
  - `cookie status`: CookieService.status() を呼び出し、cookies設定状態（存在有無・最終更新日時）をフォーマットして表示する
  - `cookie delete`: click.confirm() で確認後、CookieService.delete() で削除する。削除成功時にメッセージを表示する
  - 各コマンドのエラー（ValueError, FileNotFoundError）をキャッチしてユーザー向けメッセージを表示する
  - メインCLIエントリポイントに cookie コマンドグループを登録する
  - _Requirements: 1.1, 1.3, 3.1, 3.2, 4.1, 4.3_

- [ ] 3.2 (P) Cookie CLI のインテグレーションテスト
  - `cookie set`: stdin からの入力→ファイル保存→成功メッセージ表示の一連のフロー検証
  - `cookie set`: 空入力でエラーメッセージが表示されることの検証
  - `cookie status`: 設定済み・未設定それぞれの表示内容の検証
  - `cookie delete`: 確認→削除→成功メッセージのフロー検証
  - Click の CliRunner を使用してコマンドの入出力をテストする
  - _Requirements: 1.1, 1.3, 1.4, 3.1, 3.2, 4.1, 4.2, 4.3_

- [ ] 4. (P) YtdlpClient cookies未設定時の警告統合（タスク2に依存、タスク3と並行可）
  - `_base_opts()` で `cookie_file_path` のファイル存在を確認し、存在する場合のみ `cookiefile` オプションを設定する
  - `AuthenticationRequiredError` 発生時に、cookies.txt が存在しない場合は「cookiesが未設定です。`kirinuki cookie set` で設定してください」旨の警告をエラーメッセージに含める
  - 既存の認証エラーテストを更新し、cookies未設定時の警告メッセージを検証する
  - _Requirements: 2.3, 3.3_
