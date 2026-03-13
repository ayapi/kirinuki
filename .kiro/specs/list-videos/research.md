# Research & Design Decisions

## Summary
- **Feature**: `list-videos`
- **Discovery Scope**: Extension（既存CLIパターンの拡張）
- **Key Findings**:
  - 既存の`channel videos`コマンドがチャンネル単位の動画一覧を表示するが、全チャンネル横断の一覧表示は未対応
  - DB層に全チャンネル横断で動画を取得するメソッドが存在しない（`list_videos`・`get_latest_videos`はいずれも`channel_id`必須）
  - TUIの単一選択にはbeaupyの`select`関数を使用（既存は`select_multiple`のみ使用中）

## Research Log

### 既存の動画一覧パターン
- **Context**: 新コマンドが既存パターンとどう関わるか
- **Findings**:
  - `channel videos <channel_id>` — チャンネル単位の動画一覧。`VideoSummary`を返す
  - `db.list_videos(channel_id)` — `published_at DESC`でソート、件数制限なし
  - `db.get_latest_videos(channel_id, count)` — `COALESCE(broadcast_start_at, published_at) DESC`でソート、件数制限あり
  - 新コマンドはチャンネル横断で全動画を対象とする点が既存と異なる
- **Implications**: 新しいDBメソッドが必要。ソート順は`COALESCE(broadcast_start_at, published_at) DESC`を採用（配信日時が正確）

### beaupy単一選択
- **Context**: TUIモードで動画を1つだけ選択する必要がある
- **Findings**:
  - `from beaupy import select` で単一選択メニューを利用可能
  - `select(options, return_index=True, pagination=True, page_size=N)` — 単一インデックスを返す
  - 既存コードでは`select_multiple`のみ使用（`tui.py`）
- **Implications**: 新しいTUIヘルパー関数が必要

### segments/suggestコマンドへの連携
- **Context**: 動画選択後に既存コマンドのTUIフローに連携する
- **Findings**:
  - `segments`コマンド: `video_id`引数 → `segmentation_service.list_segments(video_id)` → TUIフロー
  - `suggest`コマンド: `--video-id`オプション → `SuggestService.suggest()` → TUIフロー
  - 両コマンドのTUIフローは`main.py`の`_run_tui_flow_segments()`と`_run_tui_flow_suggest()`で実装済み
- **Implications**: 既存のTUIフロー関数を再利用可能。CLIコマンドを直接呼ぶのではなく、内部の関数を呼び出す

## Design Decisions

### Decision: 全チャンネル横断クエリ
- **Context**: 既存メソッドはすべて`channel_id`必須
- **Alternatives Considered**:
  1. 全チャンネルIDを取得してループで`list_videos`を呼ぶ
  2. 新しいDBメソッド`get_all_videos(count)`を追加
- **Selected Approach**: 新しいDBメソッドを追加
- **Rationale**: 単一クエリの方がシンプルで効率的
- **Trade-offs**: DBメソッドが増えるが、責務は明確

### Decision: TUI単一選択関数の追加
- **Context**: 既存の`run_tui_select`はマルチセレクト専用
- **Selected Approach**: `tui.py`に`run_tui_select_one`関数を追加
- **Rationale**: 既存関数を変更せず、単一選択の新関数を追加する方が安全

## Risks & Mitigations
- beaupy `select`の動作確認 — テストで担保
- segments/suggest連携時のコンテキスト（AppContext）管理 — `create_app_context`内で実行すれば問題なし
