# Research & Design Decisions — archive-segment-extractor

## Summary
- **Feature**: `archive-segment-extractor`
- **Discovery Scope**: New Feature（既存アーキテクチャへの統合型）
- **Key Findings**:
  - yt-dlp Python APIは`YoutubeDL`クラスで動画ダウンロード可能。`extract_info(download=False)`でメタデータ事前取得、Cookie認証は`cookiefile`オプションで対応
  - ffmpegの区間切り出しは`-ss`を`-i`の前に配置 + `-c copy`でキーフレームベースの高速切り出しが可能。フレーム精度が必要な場合は再エンコード
  - 既存の`YtdlpClient` Protocolは字幕・メタデータ取得のみで動画DLメソッドが存在しない。動画ダウンロード責務を分離したProtocolを新設する

## Research Log

### yt-dlp Python API — 動画ダウンロード
- **Context**: 切り抜き元動画のオンデマンドダウンロードにyt-dlpのPython APIを使用する
- **Sources Consulted**: GitHub yt-dlp/yt-dlp リポジトリ、YoutubeDL.pyソース、PyPIドキュメント
- **Findings**:
  - `YoutubeDL(opts).download([url])`で動画DL。戻り値は`0`（成功）/`1`（失敗）
  - `extract_info(url, download=False)`でメタデータのみ取得可能（duration等）
  - Cookie認証: `cookiefile`キーにNetscape形式のCookieファイルパスを渡す
  - `cookiesfrombrowser`でブラウザから直接Cookie取得も可能だが、Windows環境でChromium系ブラウザはロック問題あり
  - 出力パス: `outtmpl`テンプレートで制御。`paths.temp`で一時DL先を指定可能
  - フォーマット選択: `format`キーで品質指定。`merge_output_format`で出力コンテナ指定
  - 例外: `DownloadError`が主要例外。`ExtractorError`, `GeoRestrictedError`等がラップされる
- **Implications**: ダウンロード専用のProtocol（`VideoDownloader`）を定義し、yt-dlpの実装詳細をインフラ層に閉じ込める

### ffmpeg subprocess — 区間切り出し
- **Context**: ダウンロードした動画から指定区間を切り出す
- **Sources Consulted**: FFmpeg公式ドキュメント、FFmpeg Wiki（Seeking）、各種技術ブログ
- **Findings**:
  - 基本コマンド: `ffmpeg -ss <start> -i input.mp4 -to <end> -c copy output.mp4`
  - `-ss`を`-i`の前に置くとキーフレームシーク（高速）、後だとフレーム精度（低速）
  - `-c copy`（ストリームコピー）: 高速だがキーフレーム精度（±数秒の誤差あり）
  - 再エンコード（`-c:v libx264 -c:a aac`）: 低速だがフレーム精度
  - 時刻形式: `HH:MM:SS.mmm`、秒数（整数・小数）、`90s`/`1500ms`等
  - ffmpeg存在確認: `shutil.which("ffmpeg")`が最も軽量
  - エラー: `subprocess.CalledProcessError`（非ゼロ終了）、`FileNotFoundError`（ffmpeg未インストール）
  - ffmpegの出力は全てstderrに書き出される
- **Implications**: `VideoClipper` Protocolを定義。デフォルトは`-c copy`（高速）、将来的にフレーム精度オプションを追加可能

### 既存アーキテクチャとの統合
- **Context**: youtube-live-clipperとarchive-clip-suggesterから呼び出し可能な設計が必要
- **Sources Consulted**: 既存spec（youtube-live-clipper/design.md、archive-clip-suggester/design.md）
- **Findings**:
  - youtube-live-clipperのNon-Goalsに「動画ファイルのダウンロード・切り抜き生成（将来フェーズ）」と明記 — 本機能がそれを担う
  - 既存`YtdlpClient` Protocolは`list_channel_video_ids`, `fetch_video_metadata`, `fetch_subtitle`の3メソッド。動画DLメソッドなし
  - `YtdlpClient`に動画DLメソッドを追加するか、別Protocolを新設するかの選択が必要
  - archive-clip-suggesterは推薦結果のセグメントデータ（video_id, start_ms, end_ms）を持つため、本モジュールへの入力として直接利用可能
- **Implications**: 動画ダウンロードは`YtdlpClient`の責務拡張として追加（同じyt-dlp依存、同じCookie認証）。ffmpegは新規Protocol。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| コア層にオーケストレーター配置 | SegmentExtractorをcore/に配置しインフラProtocolに依存 | 既存パターン準拠、テスト容易、呼び出し元から直接利用 | なし | **採用** |
| インフラ層に統合 | DL+クリップを1つのインフラコンポーネントに | シンプル | ビジネスロジック（バリデーション、クリーンアップ）がインフラに漏れる | 却下 |

## Design Decisions

### Decision: 動画ダウンロードのProtocol設計
- **Context**: 既存`YtdlpClient`は字幕・メタデータ取得のみ。動画DL機能をどこに配置するか
- **Alternatives Considered**:
  1. 既存`YtdlpClient` Protocolにダウンロードメソッドを追加
  2. 新規`VideoDownloader` Protocolを別途定義
- **Selected Approach**: 既存`YtdlpClient` Protocolに`download_video`メソッドを追加
- **Rationale**: yt-dlpの同一インスタンスでメタデータ取得もダウンロードも行う。Cookie認証設定も共有。Interface Segregationの観点では分離が理想だが、実装の自然さとCookie認証の共有を優先
- **Trade-offs**: YtdlpClientの責務が広がるが、「yt-dlpとのインテグレーション」という単一の外部依存に対するアダプターとしては妥当
- **Follow-up**: youtube-live-clipperの実装時にYtdlpClientを実装する際、download_videoも含める

### Decision: ffmpegクリッピング方式
- **Context**: ストリームコピー（高速）vs 再エンコード（フレーム精度）
- **Selected Approach**: デフォルトはストリームコピー（`-c copy`）
- **Rationale**: YouTubeアーカイブのGOPサイズ（通常2秒）を考慮すると、±2秒の精度は切り抜き用途として十分。高速でロスレス
- **Trade-offs**: キーフレーム精度のため、開始・終了が±数秒ずれる可能性がある

### Decision: 一時ファイル管理
- **Context**: DLした元動画のライフサイクル管理
- **Selected Approach**: Pythonの`tempfile.TemporaryDirectory`をコンテキストマネージャで使用
- **Rationale**: 正常終了・例外発生いずれの場合もwith文の終了時に自動クリーンアップされる。明示的なfinally処理不要
- **Trade-offs**: tempfileはOS依存だがPython標準ライブラリで十分な抽象化

## Risks & Mitigations
- **yt-dlp API安定性**: yt-dlpの内部APIは非公式。薄いラッパーで影響範囲を限定し、バージョン固定で対応
- **大容量ダウンロード**: 長時間配信（4時間超）の場合、DLに時間がかかる。進捗コールバック対応で対処
- **ffmpeg未インストール**: 実行前に`shutil.which`で存在確認、明確なエラーメッセージで案内
- **ディスク容量**: 一時ファイルとして元動画全体をDLするため一時的にストレージを消費。処理完了後に即時削除

## References
- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp) — Python API利用パターン
- [FFmpeg Wiki: Seeking](https://trac.ffmpeg.org/wiki/Seeking) — `-ss`配置による精度の違い
- [FFmpeg公式: Time Duration Format](https://ffmpeg.org/ffmpeg-utils.html#time-duration-syntax) — 時刻フォーマット仕様
