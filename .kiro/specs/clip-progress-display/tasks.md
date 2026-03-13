# Implementation Plan

- [x] 1. 進捗データモデルの定義
  - ClipPhase列挙型（ダウンロード中・再エンコード中・完了・エラーの4フェーズ）を定義する
  - ClipProgress不変データクラス（クリップ番号・フェーズ・進捗率・ダウンロード済みサイズ・合計サイズ・速度・残り時間）を定義する
  - 既存のClipOutcome等のモデルは変更しない
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. (P) yt-dlpダウンロード進捗コールバックの追加
  - download_sectionメソッドにon_progressコールバック引数を追加する
  - yt-dlpのprogress_hooksオプションを設定し、ダウンロード進捗dictをコールバック経由で外部に伝播する
  - on_progress未指定時は既存動作と完全互換を維持する
  - Cookie付きリトライ時にもprogress_hooksを維持する
  - download_sectionのon_progressが呼ばれることをモックベースで検証するテストを書く
  - _Requirements: 1.1_

- [x] 3. (P) ProgressRendererの実装
- [x] 3.1 単一クリップの進捗描画
  - ClipProgressを受け取り、フェーズに応じた1行の進捗文字列を生成するフォーマット処理を実装する（例: `ダウンロード中 45.2% | 12.3MB/27.2MB | 5.2MB/s | ETA 0:03`）
  - ダウンロード情報の一部（合計サイズ、速度、ETA等）が欠損している場合は該当部分を省略する
  - ANSIエスケープシーケンスで同一行を上書き更新する描画処理を実装する
  - 完了・再エンコード中のフェーズも適切にフォーマットする
  - フォーマット結果の文字列を検証するユニットテストを書く
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3.2 マルチクリップの全体進捗・個別進捗レイアウト
  - 1行目に全体進捗を `[完了数/全体数] 完了` 形式で表示する
  - 2行目以降に処理中のクリップ数だけ行を確保し、各行に3.1と同じフォーマットで個別進捗を表示する
  - クリップ完了時に全体進捗の完了数を更新し、完了したクリップの行を除去する
  - 前回描画した行数分カーソルを上に移動して全行を上書きする描画ロジックを実装する
  - バッファに全行を構築してから一括書き込みすることでちらつきを防止する
  - threading.Lockによるスレッドセーフな状態更新と描画を実装する
  - 非TTY環境（isatty()=False）では進捗描画をスキップするフォールバックを実装する
  - finish()メソッドで進捗行をクリアしカーソル位置を復元する
  - 内部状態の更新とマルチクリップレイアウトを検証するユニットテストを書く
  - _Requirements: 1.4, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

- [x] 4. ClipServiceの進捗コールバック拡張
  - on_progressの型をCallable[[str], None]からCallable[[ClipProgress], None]に変更する
  - yt-dlpのprogress_hooks dictをClipProgressに変換する内部ロジックを実装する（status→ClipPhase変換、downloaded_bytes/total_bytes/speed/eta抽出）
  - 再エンコード開始時と完了時にClipPhase.REENCODING / ClipPhase.DONEの通知を追加する
  - threading.Lockによる排他制御を維持する
  - download_sectionにon_progressコールバックを渡す呼び出しを追加する
  - フェーズ遷移と進捗変換の正確さを検証するユニットテストを書く
  - _Requirements: 1.1, 1.2, 1.3, 2.3, 3.2_

- [x] 5. CLIコマンド統合
  - cli/clip.pyでProgressRendererを生成し、ClipServiceのon_progressにrenderer.updateを渡す接続処理を実装する
  - 処理完了後にrenderer.finish()を呼び出して進捗行をクリアし、既存のサマリー表示に遷移する
  - 既存のサマリー表示（成功・失敗件数、個別結果）は変更しない
  - CLIコマンド実行時に進捗メッセージが出力されることを検証するテストを書く
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3_
