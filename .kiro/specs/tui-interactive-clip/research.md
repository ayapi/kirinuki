# Research & Design Decisions

## Summary
- **Feature**: `tui-interactive-clip`
- **Discovery Scope**: Extension（既存CLI拡張）
- **Key Findings**:
  - simple-term-menuが最適なTUIライブラリ（ゼロ依存、マルチセレクト対応、Windows互換）
  - 既存のClipService.execute()を単一レンジ呼び出しで再利用可能
  - SearchResult.youtube_urlから既存のextract_video_id()でvideo_id取得可能（モデル変更不要）

## Research Log

### TUIライブラリの選定
- **Context**: search/segments/suggestの結果をインタラクティブに表示し、Spaceキーで複数選択→Enterで実行するUI部品が必要
- **Sources Consulted**:
  - simple-term-menu PyPI（https://pypi.org/project/simple-term-menu/）
  - questionary PyPI（https://pypi.org/project/questionary/）
  - Textual公式ドキュメント（https://realpython.com/python-textual/）
  - InquirerPy公式ドキュメント（https://inquirerpy.readthedocs.io/）
- **Findings**:
  - **Textual**: フルTUIフレームワーク。ウィジェット豊富だが、単純な選択リストには過剰。大きな依存ツリー
  - **questionary**: prompt_toolkit依存。checkbox型でマルチセレクト対応。中程度の依存サイズ
  - **simple-term-menu**: 純Python、外部依存ゼロ。multi_select=Trueでチェックボックス選択対応。Linux/macOS/Windows対応。プレビュー機能あり
  - **InquirerPy**: prompt_toolkit依存。multiselect対応だが依存が重い
- **Implications**: simple-term-menuが「CLIファースト」の設計方針に最も適合。ゼロ依存でインストールサイズ最小、必要機能を過不足なくカバー

### 既存ClipServiceとの統合
- **Context**: TUI選択後の切り抜き実行パスの設計
- **Findings**:
  - ClipService.execute()はMultiClipRequestを受け取り、内部でbuild_numbered_filename()でファイル名生成
  - rangesが1件の場合、番号付けなしでfilenameをそのまま使用
  - TUIモードでは自動生成ファイル名を使うため、候補ごとに1リクエスト（1レンジ）で呼べば既存APIを変更せず再利用可能
- **Implications**: ClipServiceの変更不要。TUI実行層で候補をイテレートし、個別にexecute()を呼ぶ方式で統合

### SearchResultからのvideo_id取得
- **Context**: TUI選択→切り抜き実行にはvideo_idが必要だが、現在のSearchResultにvideo_idフィールドがない
- **Findings**:
  - SearchResult.youtube_urlに絶対URL（`https://www.youtube.com/watch?v={video_id}&t={seconds}`）が含まれている
  - 既存の`extract_video_id(url)`関数（clip_utils.py）でURLからvideo_idを抽出可能
  - モデル変更なしでアダプター関数内で`extract_video_id(result.youtube_url)`を呼ぶだけで対応可能
  - Segment、SegmentRecommendationにはvideo_idフィールドが直接存在
- **Implications**: SearchResultモデルの変更不要。既存ユーティリティの活用で実装コスト最小

### suggestコマンドのサービス初期化パターン
- **Context**: suggestコマンドは独自のDatabaseClient/LLMClient初期化パスを持つ（main.pyのcreate_app_contextとは別系統）
- **Findings**:
  - searchとsegmentsはcreate_app_context()経由でサービス群にアクセス
  - suggestは独自にDatabaseClient + LLMClientを生成
  - clipコマンドはYtdlpClient + ClipServiceを独自生成
  - TUIモードでは切り抜き実行のためClipServiceが追加で必要
- **Implications**: 各コマンドのTUIモード実行時にClipServiceの生成が必要。共通ヘルパー関数で生成を統一する

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Adapterパターン | 各結果型→共通ClipCandidateに変換 | 型安全、コマンド間で統一されたTUI体験 | アダプター関数のメンテナンスコスト | 採用。3種の結果型を統一的に扱える |
| 直接レンダリング | 各コマンドが独自にTUIを描画 | 実装が単純 | コード重複、一貫性欠如 | 不採用 |

## Design Decisions

### Decision: TUIライブラリにsimple-term-menuを採用
- **Context**: 軽量で複数選択可能なターミナルメニューが必要
- **Alternatives Considered**:
  1. Textual — フルTUIフレームワーク（リッチだが過剰）
  2. questionary — prompt_toolkit依存（中程度の重さ）
  3. simple-term-menu — 純Python、ゼロ依存
- **Selected Approach**: simple-term-menu
- **Rationale**: CLIファーストの方針に合致。依存ゼロで導入リスク最小。multi_select機能が要件に直接対応
- **Trade-offs**: Textualほどのリッチ表現は不可だが、選択リスト用途には十分
- **Follow-up**: Windows環境での動作確認をテストで検証

### Decision: ClipService再利用（変更なし）
- **Context**: TUI選択後の切り抜き実行方式
- **Alternatives Considered**:
  1. ClipServiceに新メソッド追加
  2. 既存execute()を1レンジずつ呼び出し
- **Selected Approach**: 既存execute()を1レンジずつ呼び出し
- **Rationale**: ClipServiceの変更が不要。rangesが1件ならファイル名がそのまま使われる既存動作を活用
- **Trade-offs**: 候補数分のexecute()呼び出しになるが、各呼び出しが独立でエラー分離が容易

### Decision: ファイル名形式 `{video_id}-{Mm}m{Ss}s-{summary}.mp4`
- **Context**: 出力ファイル名の自動生成仕様
- **Selected Approach**: `{video_id}-{分}m{秒:02d}s-{サニタイズ済み話題名}.mp4`
- **Rationale**: video_idで動画特定、時間で位置特定、話題名で内容把握。総分数表記（72m15sなど）でソート可能性とシンプルさを両立
- **Trade-offs**: 話題名が日本語の場合ファイル名が長くなりうるため、最大50文字に切り詰め

## Risks & Mitigations
- simple-term-menuのWindows互換性 — CIテストで検証。問題があればquestionary にフォールバック
- 話題名サニタイズの網羅性 — OSごとのファイル名禁止文字をカバーするサニタイズ関数を実装
- 長い結果一覧のUX — ターミナル高さに収まるスクロール表示はsimple-term-menuが自動対応

## References
- [simple-term-menu PyPI](https://pypi.org/project/simple-term-menu/) — TUIメニューライブラリ
- [questionary PyPI](https://pypi.org/project/questionary/) — 代替ライブラリ（フォールバック候補）
