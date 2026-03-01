# Implementation Plan

## Deferred Requirements
- **Requirement 4**（字幕言語の柔軟な指定）: 設計で明示的にスコープ外とした。将来対応。

## Tasks

- [x] 1. データモデル準備（SkipReason列挙型・SyncResult拡張）
- [x] 1.1 (P) SkipReasonの定義
  - 字幕スキップの理由を表す列挙型を追加する
  - `NO_SUBTITLE_AVAILABLE`（字幕データなし）、`NO_TARGET_LANGUAGE`（対象言語なし）、`PARSE_FAILED`（パース失敗）、`FETCH_FAILED`（取得失敗）の4値を定義する
  - str型を継承し、JSON等で値を直接参照可能にする
  - _Requirements: 3.3, 5.1, 5.3_

- [x] 1.2 (P) SyncResultにスキップ理由別カウントを追加
  - `skip_reasons`フィールド（辞書型: スキップ理由文字列 → カウント）を追加する
  - 既存の`skipped`フィールドは後方互換性のため維持する（総スキップ数）
  - `SyncService.sync_all()`のチャンネル横断集計でも`skip_reasons`を正しくマージする
  - _Requirements: 5.3_

- [x] 2. 字幕取得方式の根本修正（fetch_subtitle書き換え）
- [x] 2.1 fetch_subtitleをファイル書出し方式に変更
  - `extract_info(url, download=False)`を`extract_info(url, download=True)`に変更する。`skip_download=True`により動画本体のダウンロードは行わない
  - `subtitlesformat`オプションを削除し、yt-dlpにフォーマットを自動選択させる
  - 一時ディレクトリ（`tempfile.TemporaryDirectory`）に字幕を書き出し、`outtmpl`で出力先を指定する
  - `requested_subtitles["ja"]`の`filepath`フィールドから字幕ファイルパスを取得し、ファイルを読み込む
  - 戻り値を`tuple[SubtitleData | None, SkipReason | None]`に変更し、スキップ理由を呼び出し元に伝達する
  - 字幕ファイルの拡張子に応じて既存の`_parse_json3()`または新規の`_parse_vtt()`を呼び分ける
  - 一時ディレクトリはコンテキストマネージャで確実にクリーンアップする
  - _Requirements: 2.1, 2.3, 3.1, 3.2_

- [x] 2.2 VTTフォーマットの字幕パーサーを追加
  - WebVTT形式（`HH:MM:SS.mmm --> HH:MM:SS.mmm`）のタイムスタンプ行を解析し、開始時刻・継続時間をミリ秒に変換する
  - テキスト行を抽出し、HTMLタグ（`<c>`等のYouTube固有タグ含む）を除去する
  - ヘッダー行（`WEBVTT`）、空行、NOTEブロックをスキップする
  - 戻り値は既存の`SubtitleEntry`のリストとする
  - _Requirements: 2.2_

- [x] 2.3 字幕取得時の診断ログを追加
  - 字幕取得の試行時に、yt-dlpに渡すオプション辞書をDEBUGレベルでログ出力する
  - `requested_subtitles`が空の場合、レスポンスの`subtitles`・`automatic_captions`の有無と利用可能な言語・フォーマットをDEBUGログに出力する
  - 字幕ファイルが見つからない場合と、パースに失敗した場合を明確に区別してログに記録する
  - _Requirements: 1.1, 1.2, 1.3, 3.3_

- [x] 3. SyncServiceの統合（スキップ理由の記録と集計）
- [x] 3.1 _sync_single_videoをfetch_subtitleの新しい戻り値に対応
  - `fetch_subtitle()`の戻り値をタプル`(SubtitleData | None, SkipReason | None)`として受け取るように変更する
  - 字幕なしの場合、返されたSkipReasonを`SyncResult.skip_reasons`辞書に集計する
  - INFOログのスキップメッセージにスキップ理由を含める（例: `No subtitle for video {id}: {reason}`）
  - _Requirements: 1.1, 3.3, 5.2_

- [x] 4. CLI sync出力にスキップ理由の内訳を表示
- [x] 4.1 同期完了メッセージにスキップ理由別内訳を追加
  - `SyncResult.skip_reasons`の内訳を同期完了時に表示する（例: `スキップ 5件 (字幕なし: 3件, パース失敗: 2件)`）
  - スキップが0件の場合は内訳を表示しない
  - DEBUGログレベル設定時に個別のスキップ動画IDと理由が確認できることを既存のログ機構で保証する
  - _Requirements: 5.1, 5.2_

- [x] 5. テストの更新と追加
- [x] 5.1 fetch_subtitleのテストをファイル書出し方式に対応
  - 既存のモックテストを修正し、`download=True`かつ一時ディレクトリへのファイル書出しを前提としたテストに書き換える
  - 正常系: json3ファイルが書き出された場合にSubtitleDataが返ることを検証する
  - 正常系: vttファイルが書き出された場合にSubtitleDataが返ることを検証する
  - 異常系: 字幕ファイルが書き出されなかった場合に`(None, SkipReason.NO_SUBTITLE_AVAILABLE)`が返ることを検証する
  - 異常系: パース失敗時に`(None, SkipReason.PARSE_FAILED)`が返ることを検証する
  - _Requirements: 2.1, 2.2, 3.1, 3.3_

- [x] 5.2 (P) VTTパーサーのユニットテストを追加
  - 標準的なVTT形式のパースが正しく動作することを検証する
  - HTMLタグ付きテキストのタグ除去を検証する
  - 空のVTTファイル・不正なフォーマットへの耐性を検証する
  - タイムスタンプからミリ秒への変換精度を検証する
  - _Requirements: 2.2_

- [x] 5.3 (P) SyncResult・SyncService・CLI出力のテストを追加
  - `SyncResult.skip_reasons`の集計が正しく動作することを検証する
  - `SyncService._sync_single_video`がスキップ理由を正しく記録することを検証する
  - CLI出力にスキップ理由の内訳が含まれることを検証する
  - _Requirements: 5.1, 5.3_
