# Research & Design Decisions

## Summary
- **Feature**: `sync-no-subtitle-data`
- **Discovery Scope**: Extension（既存システムの字幕取得ロジック修正）
- **Key Findings**:
  - `extract_info(url, download=False)`では`requested_subtitles`の`data`フィールドが充填されない（URLのみ）
  - テストがモックで`data`フィールドを注入しているため、テストは通るが実環境で動作しない
  - `subtitlesformat: "json3"`指定が利用不可能なフォーマットの場合、字幕自体が見つからない可能性がある

## Research Log

### yt-dlp Python APIにおける`requested_subtitles`の`data`フィールド
- **Context**: 全動画で`fetch_subtitle()`が`None`を返す原因の調査
- **Sources Consulted**:
  - [yt-dlp #10561: How to properly retrieve subtitles programmatically](https://github.com/yt-dlp/yt-dlp/issues/10561)
  - [Python Help: How can get the subtitle with yt-dlp](https://discuss.python.org/t/how-can-get-the-subtitle-with-yt-dlts-python-script/35314)
  - [yt-dlp YoutubeDL.py ソースコード](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py)
- **Findings**:
  - `extract_info(url, download=False)`はメタデータ抽出のみ行い、字幕ファイルのダウンロードは行わない
  - `requested_subtitles`辞書には`url`フィールド（字幕ファイルへのURL）と`ext`フィールドが含まれるが、`data`フィールドは含まれない
  - `data`フィールドはyt-dlpのダウンロードパイプライン（`process_info()`経由）で字幕が実際にダウンロード・処理された場合にのみ充填される
  - yt-dlpメンテナーの回答: 「URLはWebVTT字幕ファイルへのもの。自分でダウンロード・パースする必要がある」
- **Implications**:
  - 現在のコード（`sub_info.get("data")`）は`download=False`では常に`None`を返す
  - テストがモックで`data`を注入しているため、テストと実環境の乖離が発生

### `download=False` vs `download=True` + `skip_download=True`
- **Context**: 字幕データを取得するための正しいAPIの使い方
- **Findings**:
  - `download=False`（`extract_info`パラメータ）: 情報抽出のみ、一切のダウンロードなし
  - `download=True` + `skip_download=True`（yt-dlpオプション）: 動画のダウンロードはスキップするが、字幕のpostprocessorは実行される
  - `download=True`の場合、字幕はファイルとしてディスクに書き出される（`data`フィールドではなく`filepath`で参照）
- **Implications**:
  - アプローチ1: `download=True`で字幕ファイルをディスクに書き出し、読み込む
  - アプローチ2: `requested_subtitles`のURLから直接HTTPで取得する
  - アプローチ3: `subtitles`/`automatic_captions`辞書からURL取得→HTTPフェッチ

### `subtitlesformat: "json3"`のフォーマット制約
- **Context**: フォーマット指定による字幕取得失敗の可能性
- **Findings**:
  - YouTubeの自動生成字幕は`json3`、`srv3`、`vtt`等の複数フォーマットで提供
  - `subtitlesformat`オプションで指定したフォーマットが利用不可の場合、`requested_subtitles`が空になる可能性
  - yt-dlpのバージョンアップでフォーマット対応が変わることがある
- **Implications**: フォーマットのフォールバック機構が必要

### `youtube-transcript-api`の代替可能性
- **Context**: yt-dlp以外の字幕取得方法の調査
- **Sources Consulted**: [youtube-transcript-api PyPI](https://pypi.org/project/youtube-transcript-api/)
- **Findings**:
  - YouTube字幕取得に特化したライブラリ
  - 構造化データ（text, start, duration）を直接返す
  - 自動生成字幕・手動字幕両方に対応
  - ただしcookie認証（メンバー限定動画）への対応が限定的
- **Implications**: メンバー限定動画対応が必要なため、yt-dlpベースの修正が優先。youtube-transcript-apiはフォールバック候補

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| URLフェッチ方式 | `requested_subtitles`のURLから直接HTTP取得 | ファイルI/O不要、シンプル | URL有効期限、認証ヘッダー管理 | yt-dlpのcookie設定が反映されない可能性 |
| ファイル書出し方式 | `download=True` + `skip_download=True`で字幕ファイル書出し→読込 | yt-dlpの全機能（認証・フォーマット変換等）を活用 | 一時ファイル管理が必要 | 最も確実なアプローチ |
| subtitles辞書直接利用 | `extract_info`の`subtitles`/`automatic_captions`辞書からURL取得 | `requested_subtitles`に依存しない | フォーマット選択ロジックを自前実装 | フォールバック戦略に柔軟 |

## Design Decisions

### Decision: 字幕データ取得方式の選定
- **Context**: `download=False`で`data`フィールドが空のため、字幕コンテンツの取得方法を変更する必要がある
- **Alternatives Considered**:
  1. URLフェッチ方式 — `requested_subtitles`のURLから直接HTTP GET
  2. ファイル書出し方式 — `download=True` + `skip_download=True`で字幕をファイルに書き出し、読み込む
  3. `youtube-transcript-api`利用 — 別ライブラリで字幕取得
- **Selected Approach**: ファイル書出し方式（Option 2）
- **Rationale**:
  - yt-dlpの認証（cookie）・フォーマット変換機能をそのまま活用できる
  - メンバー限定動画への対応が確実
  - URLフェッチ方式は認証トークン・セッション管理が別途必要になる懸念
  - `skip_download=True`で動画本体はダウンロードされないため効率面の問題なし
- **Trade-offs**:
  - 一時ファイルの生成・削除が必要（tempdir使用で対応）
  - 若干のディスクI/Oオーバーヘッド（字幕ファイルは小さいため実質無視可能）
- **Follow-up**: 一時ディレクトリのクリーンアップ戦略をtempfile.TemporaryDirectoryで実装

### Decision: フォーマットフォールバック戦略
- **Context**: `json3`が利用不可能な場合のフォールバック
- **Selected Approach**: フォーマット指定を削除し、yt-dlpのデフォルト選択に委ねる。取得後にフォーマットに応じたパーサーを呼び分ける
- **Rationale**: yt-dlpは利用可能な最適フォーマットを自動選択する機能を持っている。`subtitlesformat`を限定するとこの自動選択を阻害する
- **Trade-offs**: 複数フォーマット（json3, vtt, srv3等）のパーサー実装が必要

## Risks & Mitigations
- **一時ファイルの残存** — `tempfile.TemporaryDirectory`のコンテキストマネージャで自動クリーンアップ
- **VTTパーサーの精度** — webvtt-pyライブラリまたは正規表現ベースの軽量パーサーで対応
- **yt-dlpバージョン依存** — yt-dlp APIの安定したオプションのみ使用、テストで挙動確認

## References
- [yt-dlp #10561: Python APIでの字幕取得](https://github.com/yt-dlp/yt-dlp/issues/10561) — `requested_subtitles`はURLのみを返す
- [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md) — `skip_download`オプションの公式ドキュメント
- [youtube-transcript-api](https://pypi.org/project/youtube-transcript-api/) — 代替ライブラリの候補
