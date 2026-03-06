# Research & Design Decisions

## Summary
- **Feature**: `search-video-id-filter`
- **Discovery Scope**: Extension（既存searchコマンドへのフィルタオプション追加）
- **Key Findings**:
  - FTS検索はJOINベースのためvideo_idフィルタの追加は直接的
  - sqlite-vecのvec0テーブルはKNN検索時に任意WHERE条件を直接サポートしない
  - ベクトル検索ではオーバーフェッチ＋アプリケーション層フィルタリングが必要

## Research Log

### sqlite-vec vec0テーブルのフィルタリング制約
- **Context**: ベクトル検索に動画IDフィルタを適用する方法の調査
- **Sources Consulted**: 既存コード `database.py:443-468`、sqlite-vec仕様
- **Findings**:
  - `vec0`テーブルは `WHERE embedding MATCH ? AND k = ?` の専用構文を使用
  - この構文は追加のWHERE条件（例: `AND s.video_id IN (...)`）をKNN検索前に適用できない
  - JOINは vec0 の結果取得後に実行されるため、post-filterになる
- **Implications**: ベクトル検索でvideo_idフィルタを実現するには、kを大きめに設定してオーバーフェッチし、JOIN後にvideo_idでフィルタリングする方式が必要

### FTS検索のvideo_idフィルタリング
- **Context**: FTS5でのvideo_idフィルタ適用方法の調査
- **Sources Consulted**: 既存コード `database.py:525-555`
- **Findings**:
  - `fts_search_segments`は既にsegments→videos→channelsとJOINしている
  - `WHERE subtitle_fts MATCH ?` の後に `AND s.video_id IN (...)` を追加するだけで対応可能
  - FTS5の全文検索自体のパフォーマンスには影響なし
- **Implications**: FTS側は単純なSQLクエリ修正で対応可能

### 動画ID存在確認
- **Context**: 存在しないvideo_idが指定された場合のバリデーション方法
- **Sources Consulted**: 既存コード `database.py:222-240`（`get_video`メソッド）
- **Findings**:
  - `get_video(video_id)` で個別に存在確認可能
  - 複数IDの場合、`SELECT video_id FROM videos WHERE video_id IN (...)` で一括確認が効率的
- **Implications**: 新規メソッド `validate_video_ids` を追加し、一括確認＋存在/不在の分離を行う

## Design Decisions

### Decision: ベクトル検索のフィルタリング方式
- **Context**: vec0テーブルの制約によりKNN検索時に直接video_idフィルタを適用できない
- **Alternatives Considered**:
  1. KNN結果をオーバーフェッチし、JOIN後にアプリケーション層でフィルタ
  2. video_id別にKNNを個別実行し結果をマージ
- **Selected Approach**: オプション1 — オーバーフェッチ＋post-filter
- **Rationale**: SQLクエリ1回で完結、既存クエリ構造との差分が最小、video_id数に依存しない安定した性能
- **Trade-offs**: フィルタ後に結果数がlimitを下回る可能性がある（kのオーバーフェッチ倍率で緩和）
- **Follow-up**: オーバーフェッチ倍率はデフォルト5倍程度とし、十分な結果が得られることを確認

### Decision: フィルタパラメータの伝播方式
- **Context**: CLI → SearchService → Database の各層へvideo_idsを伝播する方法
- **Alternatives Considered**:
  1. 各メソッドにオプショナル引数 `video_ids: list[str] | None` を追加
  2. フィルタ条件を包含するSearchQueryオブジェクトを導入
- **Selected Approach**: オプション1 — オプショナル引数の追加
- **Rationale**: 変更が最小限で済む。将来的にフィルタ条件が増えた場合にSearchQueryへのリファクタリングは可能
- **Trade-offs**: フィルタ条件が3つ以上に増えた場合はリファクタリングが必要

## Risks & Mitigations
- **ベクトル検索のオーバーフェッチで結果不足** — 倍率を調整可能にし、デフォルト5倍で開始。フィルタ対象動画が少数の場合は十分
- **大量のvideo_id指定時のIN句性能** — 実用上数十件程度を想定、SQLiteのIN句制限（デフォルト999パラメータ）内で収まる
