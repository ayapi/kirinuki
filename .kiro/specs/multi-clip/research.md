# Research & Design Decisions

## Summary
- **Feature**: `multi-clip`
- **Discovery Scope**: Extension（既存 clip コマンドの再設計）
- **Key Findings**:
  - yt-dlp は `--download-sections` CLI オプション / `download_ranges` Python API パラメータで範囲指定ダウンロードをネイティブサポートしている
  - YouTube の DASH 形式では、yt-dlp は必要なフラグメントのみをダウンロードできるため、丸ごとDLより帯域・時間効率が良い
  - `download_range_func(None, [(start1, end1), (start2, end2)])` で複数範囲を1回の呼び出しで指定可能
  - ただし既知の問題あり（HLS形式での空ファイル、一部フォーマットでの映像欠落）。`format_sort: ['proto:https']` で DASH を優先することで回避可能
  - `AppConfig` に `output_dir` が未定義。`pydantic_settings` の仕組みで環境変数・設定ファイル両対応で追加可能

## Research Log

### yt-dlp の範囲指定ダウンロード機能調査
- **Context**: 現在の「丸ごとDL → ffmpeg切り出し」方式に代わる、yt-dlp ネイティブの範囲指定DLの存在と実用性の調査
- **Sources Consulted**:
  - [yt-dlp GitHub リポジトリ](https://github.com/yt-dlp/yt-dlp) — `download_ranges` パラメータのドキュメント
  - [Issue #10181](https://github.com/yt-dlp/yt-dlp/issues/10181) — 範囲指定DLの効率に関する議論
  - [Issue #8756](https://github.com/yt-dlp/yt-dlp/issues/8756) — Python API での `download_ranges` 使用例
  - [Issue #9328](https://github.com/yt-dlp/yt-dlp/issues/9328) — `download_range_func` の使い方とHLS形式での問題
- **Findings**:
  - **CLI**: `--download-sections "*START-END"` で時間範囲指定。複数回指定で複数範囲
  - **Python API**: `download_ranges` パラメータに `download_range_func(None, [(s1, e1), (s2, e2)])` を渡す
  - **内部動作（DASH形式）**: YouTubeのDASH形式では、yt-dlp は指定時間範囲に該当するフラグメントのみをダウンロードする。丸ごとDLではない
  - **内部動作（非フラグメント形式）**: 全体をDLしてからffmpegでトリム
  - **`force_keyframes_at_cuts`**: キーフレーム位置で正確にカットするオプション。有効にすると再エンコードが必要で低速。無効だとキーフレーム境界でカット（`-c copy` と同等）
  - **既知の問題**: HLS形式で空ファイルが生成されるケースあり。`format_sort: ['proto:https']` でDASHを優先することで回避
  - **複数範囲の出力**: 各範囲ごとに別ファイルとして出力される。ファイル名テンプレートで `%(section_start)s` 等が使える
- **Implications**:
  - **FfmpegClient は不要になる可能性が高い**: yt-dlp が内部でffmpegを使ってDL+トリムを一体処理するため、別途ffmpegを呼ぶ必要がない
  - **YtdlpClient の拡張のみで対応可能**: `download_video()` に代わる `download_sections()` メソッドを追加
  - **帯域効率が大幅改善**: 2時間の配信から2分×3箇所を切り抜く場合、約6分ぶんのフラグメントのみDL（従来は120分ぶん全DL）

### 既存 clip コマンドの構造分析
- **Context**: 現在のCLI引数構成と変更範囲の特定
- **Findings**:
  - CLI: `clip <video> <start> <end> <output>` — 位置引数4つ
  - Core: `ClipService.execute(request, on_progress)` — 単一 `ClipRequest` → `ClipResult`
  - Infra: `FfmpegClientImpl.clip(input, output, start, end)` — yt-dlp方式採用により不要になる
  - Infra: `YtdlpClient.download_video(video_id, output_dir, cookie_file)` — `download_sections()` に置き換え
- **Implications**: CLI層とサービス層の変更が主体。Infra層は `YtdlpClient` に新メソッド追加、`FfmpegClient` は clip コマンドでは使わない

### 時間範囲パーサーの設計
- **Context**: `18:03-19:31,21:31-23:20` のカンマ区切り形式のパース方法
- **Findings**:
  - 既存の `parse_time_str()` は `HH:MM:SS`, `MM:SS`, 秒数をサポート
  - 新たに `START-END` 形式（ハイフン区切り）のペアパースが必要
  - カンマで分割 → 各要素をハイフンで分割 → `parse_time_str()` で変換の3段階
- **Implications**: `clip_utils.py` に `parse_time_ranges()` 関数を追加。既存 `parse_time_str()` はそのまま再利用

### 出力ファイル名の連番ロジック
- **Context**: `動画.mp4` → `動画1.mp4`, `動画2.mp4` の命名規則
- **Findings**:
  - `Path.stem` と `Path.suffix` で分離し、連番を挿入
  - 単一範囲の場合は連番なし
  - 1始まりの連番（ゼロパディングなし）
- **Implications**: `clip_utils.py` に `build_numbered_filename()` を追加

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A: 丸ごとDL + ffmpeg切り出し | 動画全体をDL → ffmpegで各範囲を切り出し | シンプル、確実、既存実装の延長 | 長時間動画で帯域・時間が無駄 | 前回設計で採用していた方式 |
| B: yt-dlp download_ranges | yt-dlp の範囲指定DLで必要フラグメントのみ取得 | 帯域効率が良い、ffmpeg別呼び出し不要 | HLS形式での既知問題、yt-dlp API依存 | **採用**: DASH優先設定で問題回避可能 |
| C: yt-dlp + ffmpeg外部呼び出し (Gist方式) | ffmpeg_i引数で-ss/-toを渡してDL時にトリム | ffmpegの柔軟性を活用 | undocumented、不安定 | 不採用: 公式APIの方が安定 |

## Design Decisions

### Decision: yt-dlp `download_ranges` の採用（設計変更）
- **Context**: 丸ごとDL + ffmpeg方式 vs yt-dlp ネイティブ範囲指定DL方式
- **Alternatives Considered**:
  1. 丸ごとDL → ffmpegで複数回切り出し（前回設計）
  2. yt-dlp `download_ranges` でフラグメントレベルの部分DL
- **Selected Approach**: yt-dlp `download_ranges` を使用。`YtdlpClient` に `download_sections()` メソッドを追加
- **Rationale**:
  - 長時間配信からの切り抜きがメインユースケース。2時間配信から数分の切り抜きなら、帯域使用量が大幅に削減される
  - yt-dlp が内部でffmpegを呼ぶため、自前のffmpeg呼び出しが不要になりアーキテクチャが簡素化
  - `format_sort: ['proto:https']` でDASHを優先すれば、HLS形式の既知問題を回避可能
- **Trade-offs**:
  - yt-dlp の内部API（`download_range_func`）への依存が増す
  - キーフレーム境界での精度は `-c copy` 方式と同等（`force_keyframes_at_cuts` を使わない限り）
- **Follow-up**: yt-dlp のバージョンアップで `download_range_func` の仕様が変わる可能性があるため、ラッパー層で吸収する

### Decision: CLI引数の設計
- **Context**: `<video> <filename> <time_ranges>` の3引数構成
- **Selected Approach**: Click の位置引数3つ + `--output-dir` オプション
- **Rationale**: ユーザーのフィードバックに忠実。シンプルで直感的

## Risks & Mitigations
- yt-dlp `download_range_func` のAPI変更 → `YtdlpClient` のラッパー層で吸収。テストでAPI互換性を検証
- HLS形式での空ファイル生成 → `format_sort: ['proto:https']` でDASH優先。フォールバックとして丸ごとDL方式を検討
- 時間範囲文字列に不正文字が含まれる場合 → バリデーション段階で全範囲を検証し、不正があれば処理前にエラー
- 出力ディレクトリの権限不足 → ディレクトリ作成時にOSError をキャッチして報告

## References
- [yt-dlp GitHub リポジトリ](https://github.com/yt-dlp/yt-dlp) — `download_ranges` ドキュメント
- [Issue #10181: 範囲指定DLの効率](https://github.com/yt-dlp/yt-dlp/issues/10181)
- [Issue #8756: Python API での download_ranges](https://github.com/yt-dlp/yt-dlp/issues/8756)
- [Issue #9328: download_range_func の使い方](https://github.com/yt-dlp/yt-dlp/issues/9328)
- [Issue #5926: --download-sections での映像欠落](https://github.com/yt-dlp/yt-dlp/issues/5926)
