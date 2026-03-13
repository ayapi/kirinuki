# Research & Design Decisions

## Summary
- **Feature**: `clip-progress-display`
- **Discovery Scope**: Extension
- **Key Findings**:
  - yt-dlpは`progress_hooks`オプションでダウンロード進捗コールバックを提供しており、`downloaded_bytes`・`total_bytes`・`speed`・`eta`・`status`等を取得可能
  - ffmpegのsubprocess実行は`capture_output=True`で標準出力を抑制しているため、再エンコードの詳細な進捗率取得はコスト高（`-progress`パイプ + パース要）。スピナーまたは「再エンコード中...」表示が妥当
  - ANSIエスケープシーケンス（カーソル移動 + 行クリア）で複数行の上書き更新が可能。対象ターミナル（MSYS2/Git Bash, Linux, macOS）はすべてANSI対応

## Research Log

### yt-dlp progress_hooks API
- **Context**: ダウンロード進捗をリアルタイム取得する方法の調査
- **Sources Consulted**: yt-dlp公式ドキュメント、ソースコード
- **Findings**:
  - `YoutubeDL`コンストラクタの`progress_hooks`オプションにコールバック関数のリストを渡せる
  - コールバックは`dict`を受け取り、主要なキーは:
    - `status`: `"downloading"` | `"finished"` | `"error"`
    - `downloaded_bytes`: ダウンロード済みバイト数
    - `total_bytes` or `total_bytes_estimate`: 合計サイズ（推定含む）
    - `speed`: ダウンロード速度（bytes/sec）
    - `eta`: 残り時間（秒）
    - `_percent_str`: フォーマット済みパーセント文字列
    - `filename`: 出力ファイル名
  - DASH形式の場合、映像・音声が別トラックとしてダウンロードされるため、progress_hooksは各トラックで個別に呼ばれる
- **Implications**: `download_section()`にprogress_hookを渡すことで、ダウンロード進捗を取得可能。DASHの2トラック問題は、合算または最新トラックの進捗を表示する方針で対応

### ffmpeg再エンコード進捗
- **Context**: ffmpegの処理進捗を取得する方法の調査
- **Findings**:
  - ffmpegの`-progress`オプションでパイプに進捗情報を出力可能だが、`subprocess.run()`の変更（Popenへの置き換え + パイプ読み取り）が必要
  - 再エンコードは通常数秒〜数十秒（clipは短い区間のため）で完了
  - 投資対効果の観点から、「再エンコード中...」のステータス表示で十分
- **Implications**: ffmpegの進捗率取得は将来の拡張とし、現時点はステータス表示のみ

### ターミナル複数行上書き方法
- **Context**: 並列処理中の複数行進捗を同時表示・更新する方法
- **Findings**:
  - ANSIエスケープシーケンス: `\033[nA`（n行上に移動）、`\033[2K`（行クリア）、`\r`（行頭に戻る）
  - 対象ターミナル（MSYS2/Git Bash, Linux Terminal, macOS Terminal）はすべてANSI対応
  - `rich`ライブラリのLive/Progressは高機能だが新規依存追加が必要
  - `sys.stderr.write()` + `flush()`で直接制御が最もシンプル
- **Implications**: 新規ライブラリを追加せず、ANSIエスケープシーケンスで実装

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| ANSIエスケープ直接 | sys.stderrにANSIシーケンスを直接書き込む | 依存なし、シンプル | Windows cmd.exe非対応（MSYS2は対応） | プロジェクトのターゲット環境に適合 |
| rich Progress | richライブラリのProgressバーを使用 | 高機能、美麗 | 新規依存追加、学習コスト | オーバースペック |
| click.echo + \r | click.echoで単一行更新 | click統一 | 複数行同時更新不可 | マルチクリップ要件に非適合 |

## Design Decisions

### Decision: ANSIエスケープシーケンスによるターミナル描画
- **Context**: マルチクリップ時に複数行を同時に上書き更新する必要がある
- **Alternatives Considered**:
  1. `rich`ライブラリ — 高機能だが新規依存
  2. ANSIエスケープ直接制御 — 依存なし、対象環境で動作確認済み
  3. click.echo + `\r` — 単一行のみ対応
- **Selected Approach**: ANSIエスケープシーケンスによる直接制御
- **Rationale**: プロジェクトのターゲット環境（MSYS2/Git Bash, Linux, macOS）はすべてANSI対応。新規依存を追加せず、必要十分な機能を実現可能
- **Trade-offs**: Windows cmd.exeでは非対応だが、プロジェクトのターゲット外
- **Follow-up**: 非ターミナル環境（パイプリダイレクト等）では進捗表示を無効化する

### Decision: ProgressRendererの責務分離
- **Context**: 進捗表示ロジックをどの層に配置するか
- **Selected Approach**: CLI層に`ProgressRenderer`を新設し、コア層はデータモデル（`ClipProgress`）のみを定義
- **Rationale**: コア層はターミナル表示に依存すべきでない。CLI→コア→インフラの3層分離原則を維持

## Risks & Mitigations
- **DASHトラック分離による進捗の不正確さ** — 映像・音声トラックの合算ではなく、現在ダウンロード中のトラックの進捗を表示。`finished`ステータスでリセット
- **非ターミナル環境での表示崩れ** — `sys.stderr.isatty()`で判定し、非TTY環境では簡易メッセージにフォールバック
- **yt-dlpの`total_bytes`が取得できないケース** — `total_bytes_estimate`をフォールバックに使用。いずれも取得できない場合はサイズ情報なしで表示
