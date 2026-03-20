# Research & Design Decisions

## Summary
- **Feature**: `clip-margin`
- **Discovery Scope**: Extension（既存システムへの機能追加）
- **Key Findings**:
  - `MultiClipRequest`にフィールド追加するだけでリクエスト単位のマージン制御が実現可能
  - `ClipService._process_one()`内でマージン適用するのが最も適切（全実行パスを一箇所でカバー）
  - TUI `execute_clips`がMultiClipRequest構築の唯一のTUI側エントリポイント

## Research Log

### マージン適用箇所の検討
- **Context**: マージンをどの層で適用するのが最適か
- **Sources Consulted**: `core/clip_service.py`, `cli/tui.py`, `cli/clip.py`, `models/clip.py`のソースコード分析
- **Findings**:
  - `ClipService.execute()`は全切り抜きパス（CLI/TUI）の共通エントリポイント
  - `_process_one()`内で`time_range.start_seconds`と`time_range.end_seconds`が直接`download_section`に渡される
  - マージンをここで適用すれば、TimeRangeモデル自体は変更不要（元の範囲を保持）
- **Implications**: ClipServiceでマージンを適用し、MultiClipRequestにフィールドを追加する設計が最も影響範囲が小さい

### TUI/CLIのエントリポイント分析
- **Context**: TUIとCLIで異なるマージン動作を実現する方法
- **Sources Consulted**: `cli/tui.py:execute_clips`, `cli/clip.py:clip`
- **Findings**:
  - TUI: `execute_clips()`が`MultiClipRequest`を構築（L246-252）
  - CLI: `clip()`コマンドが`MultiClipRequest`を構築（L84-90）
  - 両者とも独立にMultiClipRequestを生成するため、`margin_seconds`フィールドの設定箇所を分けるだけで実現可能
- **Implications**: TUI側で`margin_seconds=5.0`を設定、CLI側は`0.0`（デフォルト）のまま

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| MultiClipRequestフィールド追加 | margin_secondsをリクエストモデルに追加 | リクエスト単位で制御可能、既存モデルの自然な拡張 | なし | 採用 |
| ClipServiceコンストラクタ引数 | margin_secondsをサービス初期化時に設定 | シンプル | リクエスト単位で変更不可 | 却下: Req 3.2に不適合 |
| TimeRangeにマージン組み込み | TimeRange生成時にマージンを適用 | 早期適用 | 元の範囲情報が失われる、既存バリデーションとの整合性問題 | 却下 |

## Design Decisions

### Decision: マージンをMultiClipRequestフィールドとして追加
- **Context**: リクエスト単位でマージン適用を制御する必要がある（Req 3.2）
- **Alternatives Considered**:
  1. MultiClipRequestにフィールド追加 — 呼び出し元がリクエスト生成時に設定
  2. ClipServiceコンストラクタ引数 — サービス初期化時に固定
  3. TimeRangeモデル側で吸収 — 元の範囲情報が消失
- **Selected Approach**: MultiClipRequestに`margin_seconds: float = 0.0`を追加
- **Rationale**: リクエスト単位の制御が可能、デフォルト0.0で後方互換性を保持、既存のコード変更が最小限
- **Trade-offs**: フィールドが増えるが、Pydanticモデルの自然な拡張パターンに沿っている
- **Follow-up**: テストでマージン適用・非適用の両パスを検証

### Decision: マージン適用をClipService._process_oneで実行
- **Context**: download_sectionに渡すstart/end値にマージンを反映する必要がある
- **Selected Approach**: `_process_one()`内でrequest.margin_secondsを参照し、start/endを調整してからdownload_sectionに渡す
- **Rationale**: 一箇所でカバーでき、TimeRangeの元の値（ClipOutcome.range）は変更されない

### Decision: デフォルト値の定数定義
- **Context**: マージン秒数のデフォルト値を明示的に管理する（Req 3.1）
- **Selected Approach**: `core/clip_service.py`にモジュールレベル定数`DEFAULT_CLIP_MARGIN_SECONDS = 5.0`を定義
- **Rationale**: ClipServiceと同モジュールに置くことで凝集度が高い。TUI側からはこの定数をインポートして使用

## Risks & Mitigations
- マージンによる開始時刻が負になる → `max(0, start - margin)`でクランプ（Req 1.2）
- マージンによる終了時刻が動画長を超える → yt-dlpが自動的に動画末尾で切り捨て（Req 1.3）
- 既存テストへの影響 → デフォルト`margin_seconds=0.0`により既存テストは変更不要
