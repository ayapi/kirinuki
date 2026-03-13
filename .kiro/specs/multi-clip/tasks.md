# Implementation Plan

- [x] 1. データモデルと設定の拡張
- [x] 1.1 (P) 複数範囲リクエスト・結果モデルの作成
  - 開始・終了秒数のペアを表す TimeRange モデルを作成し、開始 < 終了、開始 >= 0 のバリデーションを実装する
  - 動画ID・ファイル名・出力先ディレクトリ・TimeRange リストを持つ MultiClipRequest モデルを作成し、ranges が1つ以上であることを検証する
  - 個別の切り出し結果（成功時の出力パス、失敗時のエラーメッセージ）を持つ ClipOutcome モデルを作成する
  - 全切り出し結果を集約する MultiClipResult モデルを作成し、成功数・失敗数のプロパティを実装する
  - 既存の ClipRequest / ClipResult は他の箇所から参照がなければ削除する
  - _Requirements: 2.3_

- [x] 1.2 (P) 出力先ディレクトリの設定項目を追加
  - AppConfig に output_dir フィールドを追加し、デフォルト値を `~/.kirinuki/output` とする
  - 環境変数 `KIRINUKI_OUTPUT_DIR` および設定ファイル `.env` の両方から読み込めることを確認する
  - _Requirements: 4.1_

- [x] 2. ユーティリティ関数の追加
- [x] 2.1 カンマ区切り時間範囲パーサーの実装
  - `18:03-19:31,21:31-23:20` 形式のカンマ区切り文字列を受け取り、TimeRange のリストに変換する関数を作成する
  - 単一範囲（カンマなし、例: `18:03-19:31`）も正常にパースする
  - 既存の時刻パース関数（`HH:MM:SS`, `MM:SS`, 秒数）を再利用し、ハイフン区切りの開始・終了を分離する
  - 不正なフォーマット（ハイフンなし、空文字列、時刻として無効な値）の場合は ValueError を送出する
  - タスク 1.1 の TimeRange モデルに依存する
  - _Requirements: 1.2, 1.3, 2.3_

- [x] 2.2 連番ファイル名生成関数の実装
  - ベースファイル名と連番インデックス・総数を受け取り、連番付きファイル名を返す関数を作成する
  - 複数範囲の場合は拡張子の前に連番を挿入する（例: `動画.mp4` → `動画1.mp4`, `動画2.mp4`）
  - 単一範囲（総数が1）の場合は連番を付与せずそのまま返す（例: `動画.mp4`）
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 3. (P) YtdlpClient に範囲指定ダウンロードメソッドを追加
  - yt-dlp の `download_range_func` API を使って指定時間範囲のフラグメントのみをダウンロードする `download_section` メソッドを実装する
  - DASH形式を優先するため `format_sort: ['proto:https']` を設定し、HLS形式の既知問題を回避する
  - 出力先パスを `outtmpl` で指定し、yt-dlp が直接そのパスに書き込むようにする
  - Cookie認証の引き継ぎ（既存の `download_video` と同じロジック）を実装する
  - ダウンロード失敗時は既存の VideoDownloadError、認証エラー時は AuthenticationRequiredError を送出する
  - _Requirements: 2.1_

- [x] 4. ClipService の複数範囲対応への再設計
  - `execute()` メソッドを MultiClipRequest を受け取り MultiClipResult を返すように変更する
  - コンストラクタから FfmpegClient 依存を削除し、YtdlpClient のみに依存するようにする
  - 出力先ディレクトリが存在しない場合に自動作成する処理を追加する
  - 各 TimeRange に対して `YtdlpClient.download_section()` を順次呼び出し、成功/失敗を ClipOutcome として記録する
  - 個別の切り出しが失敗した場合はエラーを記録して残りの範囲の処理を続行する
  - 進捗コールバックで現在の処理番号と総数を通知する（例: `[2/5] 切り抜き中...`）
  - タスク 1.1 のモデルとタスク 3 の download_section に依存する
  - _Requirements: 2.1, 2.2, 4.3, 5.1, 5.2, 5.4_

- [x] 5. CLI clip コマンドの刷新
  - 既存の clip コマンドの引数を `<video> <filename> <time_ranges>` の3つの位置引数に変更する
  - `--output-dir` オプションを追加し、指定時はCLI引数を、未指定時は AppConfig の output_dir をデフォルトとして使用する
  - CLI 層で時間範囲文字列のパースとバリデーションを行い、エラー時は不正な範囲を特定するメッセージを表示する
  - パース済みデータと連番ファイル名から MultiClipRequest を組み立て、ClipService.execute() を呼び出す
  - 処理完了後に成功数・失敗数のサマリーと各ファイルの出力パスを表示する
  - 動画DL失敗、認証エラーなどの例外を適切にキャッチして日本語エラーメッセージを表示する
  - タスク 1, 2, 4 に依存する
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.2, 5.1, 5.3_

- [x] 6. テスト
- [x] 6.1 モデルとユーティリティのユニットテスト
  - TimeRange のバリデーション（正常系、開始 >= 終了、負の値）をテストする
  - MultiClipRequest のバリデーション（正常系、空リスト）をテストする
  - MultiClipResult の success_count / failure_count プロパティをテストする
  - parse_time_ranges の正常系（単一、複数、各時刻フォーマット）と異常系（不正フォーマット、逆順、空文字列）をテストする
  - build_numbered_filename の単一時（連番なし）、複数時（連番あり）をテストする
  - _Requirements: 1.2, 1.3, 2.3, 3.1, 3.2, 3.3_

- [x] 6.2 ClipService のインテグレーションテスト
  - YtdlpClient をモック化し、複数範囲の正常処理フローを検証する
  - 3範囲中1つが失敗するシナリオで、残り2つが成功し結果が正しく集約されることを検証する
  - 出力先ディレクトリが存在しない場合に自動作成されることを検証する
  - 進捗コールバックが正しい処理番号で呼ばれることを検証する
  - _Requirements: 2.1, 2.2, 4.3, 5.1, 5.2, 5.4_

- [x] 6.3 CLI の E2E テスト
  - click の CliRunner を使い、正常な引数でコマンドが成功することを検証する
  - `--output-dir` オプションが AppConfig よりも優先されることを検証する
  - 不正な時間範囲が指定された場合にエラーメッセージが表示されることを検証する
  - 複数範囲の処理後にサマリーが表示されることを検証する
  - _Requirements: 1.1, 1.4, 4.2, 5.3_

- [ ] 7. 日時プレフィックスのユーティリティ関数とモデル拡張
- [ ] 7.1 (P) 日時プレフィックス生成・付与・重複検出の関数を追加
  - 配信開始日時（UTC or tz-aware）をJST（Asia/Tokyo）に変換し `YYYYMMDD_HHMM_` 形式の文字列を生成してファイル名の先頭に付与する関数を実装する
  - 配信開始日時が None の場合はファイル名をそのまま返す
  - ファイル名が既に `YYYYMMDD_HHMM_` 形式のプレフィックスを持つかを正規表現で判定する関数を実装する
  - プレフィックスが既に存在する場合は重複付与せずそのまま返す
  - _Requirements: 6.1, 6.2, 6.5, 6.6_

- [ ] 7.2 (P) MultiClipRequest に配信開始日時フィールドを追加
  - MultiClipRequest モデルに `broadcast_start_at`（datetime | None、デフォルト None）フィールドを追加する
  - 既存のバリデーションや他フィールドへの影響がないことを確認する
  - _Requirements: 6.1_

- [ ] 8. ClipService のファイル名構築に日時プレフィックスを適用
  - ClipService がファイル名を構築する際に、連番付与後に日時プレフィックス関数を呼び出してプレフィックスを付与する
  - `filenames` リスト指定時（TUI経由）も各ファイル名に対して同様にプレフィックスを適用する
  - `broadcast_start_at` が None の場合はプレフィックスなしで従来通り動作する
  - タスク 7.1, 7.2 に依存する
  - _Requirements: 6.1, 6.3, 6.4_

- [ ] 9. CLI・TUI での配信開始日時の取得と受け渡し
- [ ] 9.1 (P) CLI clip コマンドでメタデータを取得し broadcast_start_at を設定
  - clip コマンド実行時に YtdlpClient.fetch_video_metadata() で動画のメタデータを取得する
  - broadcast_start_at を取得し、未取得の場合は published_at にフォールバックする
  - メタデータ取得失敗時はワーニングを表示し broadcast_start_at=None で処理を続行する
  - 取得した日時を MultiClipRequest の broadcast_start_at に設定する
  - タスク 8 に依存する
  - _Requirements: 6.1, 6.2_

- [ ] 9.2 (P) TUI execute_clips でメタデータを取得し broadcast_start_at を設定
  - TUI の execute_clips で各動画グループの処理前に fetch_video_metadata() を呼び出す
  - broadcast_start_at（フォールバック: published_at）を MultiClipRequest に設定する
  - メタデータ取得失敗時はワーニングを表示し broadcast_start_at=None で続行する
  - タスク 8 に依存する
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 10. 日時プレフィックス機能のテスト
- [ ] 10.1 (P) ユーティリティ関数のユニットテスト
  - UTC の datetime を渡した場合に JST 変換された `YYYYMMDD_HHMM_` プレフィックスが付与されることを検証する
  - broadcast_start_at が None の場合にプレフィックスなしのファイル名がそのまま返ることを検証する
  - 既にプレフィックスが付いたファイル名に対して重複付与されないことを検証する
  - 日時プレフィックスと連番の組み合わせ（例: `20260310_2100_動画1.mp4`）が正しいことを検証する
  - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.6_

- [ ] 10.2 (P) ClipService のインテグレーションテスト
  - broadcast_start_at 付きの MultiClipRequest で execute() を呼び出し、出力ファイル名に日時プレフィックスが付与されることを検証する
  - broadcast_start_at=None の場合にプレフィックスなしで出力されることを検証する
  - filenames リスト指定時にも各ファイル名にプレフィックスが付与されることを検証する
  - _Requirements: 6.1, 6.3, 6.4_
