# Requirements Document

## Introduction
指定したYouTubeLiveアーカイブURLの指定した区間だけを切り抜いた動画を生成する機能。
本モジュールはプロジェクトのコア機能「オンデマンドクリッピング」の実体であり、yt-dlpによる動画取得とffmpegによる区間切り出しを組み合わせて動作する。
将来的に `youtube-live-clipper`（CLI層）や `archive-clip-suggester`（推薦エンジン）から呼び出されるライブラリ的なモジュールとして設計する。

## Requirements

### Requirement 1: 区間指定による切り抜き動画生成
**Objective:** As a 開発者/利用者, I want YouTubeLiveアーカイブURLと開始・終了時刻を指定して切り抜き動画を生成したい, so that 長時間アーカイブから必要な部分だけを効率的に取り出せる

#### Acceptance Criteria
1. When アーカイブURLと開始時刻・終了時刻が指定された場合, the SegmentExtractor shall 指定区間のみを切り出した動画ファイルを生成する
2. When 開始時刻のみが指定された場合, the SegmentExtractor shall 開始時刻から動画末尾までを切り出す
3. When 終了時刻のみが指定された場合, the SegmentExtractor shall 動画冒頭から終了時刻までを切り出す
4. The SegmentExtractor shall 時刻指定を `HH:MM:SS` または秒数（整数・小数）の両形式で受け付ける
5. When 切り抜き動画の生成が完了した場合, the SegmentExtractor shall 生成された動画ファイルのパスを返却する

### Requirement 2: オンデマンドダウンロードとクリーンアップ
**Objective:** As a システム, I want 切り抜き実行時にのみ動画をダウンロードし、完了後に元動画を即時削除したい, so that ストレージを最小限に抑えられる

#### Acceptance Criteria
1. When 切り抜きが要求された場合, the SegmentExtractor shall yt-dlpを使用して対象動画を一時ディレクトリにダウンロードする
2. When 切り抜き動画の生成が完了した場合, the SegmentExtractor shall ダウンロードした元動画ファイルを即時削除する
3. If 切り抜き処理中にエラーが発生した場合, the SegmentExtractor shall ダウンロードした一時ファイルをクリーンアップしてから例外を送出する
4. The SegmentExtractor shall 一時ファイルをシステムの一時ディレクトリまたは設定可能なディレクトリに保存する

### Requirement 3: 出力制御
**Objective:** As a 利用者, I want 出力先パスや動画フォーマットを指定したい, so that 用途に応じた形式で切り抜き動画を得られる

#### Acceptance Criteria
1. The SegmentExtractor shall 出力先ファイルパスを指定可能とする
2. When 出力先パスが指定されなかった場合, the SegmentExtractor shall カレントディレクトリに自動生成されたファイル名で保存する
3. The SegmentExtractor shall 出力フォーマット（mp4等）を指定可能とする
4. When 出力フォーマットが指定されなかった場合, the SegmentExtractor shall mp4をデフォルトとして使用する

### Requirement 4: 認証対応（メンバー限定動画）
**Objective:** As a 利用者, I want メンバー限定配信のアーカイブも切り抜きたい, so that 限定コンテンツからも必要な区間を抽出できる

#### Acceptance Criteria
1. Where Cookie認証情報が設定されている場合, the SegmentExtractor shall メンバー限定動画をダウンロードして切り抜きを実行する
2. Where Cookie認証情報が設定されている場合, the SegmentExtractor shall yt-dlpのCookie認証機構を利用してアクセスする
3. If 認証が必要な動画に対してCookie情報が未設定の場合, the SegmentExtractor shall 認証が必要である旨のエラーを返す

### Requirement 5: エラーハンドリング
**Objective:** As a 利用者/呼び出し元モジュール, I want エラー発生時に原因がわかる明確なエラー情報を得たい, so that 問題の特定と対処が迅速にできる

#### Acceptance Criteria
1. If 無効なYouTube URLが指定された場合, the SegmentExtractor shall URLが不正である旨のエラーを返す
2. If 指定した時間範囲が動画の長さを超えている場合, the SegmentExtractor shall 時間範囲が不正である旨のエラーを返す
3. If 開始時刻が終了時刻より後に指定された場合, the SegmentExtractor shall 時間範囲の順序が不正である旨のエラーを返す
4. If ffmpegがシステムにインストールされていない場合, the SegmentExtractor shall ffmpegが必要である旨のエラーを返す
5. If 動画のダウンロードに失敗した場合, the SegmentExtractor shall ダウンロード失敗の原因を含むエラーを返す

### Requirement 6: プログラマティックインターフェース
**Objective:** As a 他モジュール（youtube-live-clipper, archive-clip-suggester）, I want Pythonの関数/クラスとしてこの機能を呼び出したい, so that CLI経由ではなくプログラム的に切り抜きを実行できる

#### Acceptance Criteria
1. The SegmentExtractor shall Pythonの公開APIとして利用可能なクラスまたは関数を提供する
2. The SegmentExtractor shall 入力パラメータをPydanticモデルで定義し、バリデーションを提供する
3. The SegmentExtractor shall 処理結果を構造化されたオブジェクト（Pydanticモデル）として返却する
4. The SegmentExtractor shall コア層（`core/`）に配置し、インフラ層への依存をインターフェース経由で注入可能とする
