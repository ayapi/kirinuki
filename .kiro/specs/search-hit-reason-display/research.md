# Research & Design Decisions

## Summary
- **Feature**: `search-hit-reason-display`
- **Discovery Scope**: Extension（既存の検索機能への拡張）
- **Key Findings**:
  - FTS検索クエリを修正し、マッチした字幕テキストを同時に取得可能
  - ベクトル検索のdistanceは既に返却されており、類似度変換のみ必要
  - SearchResultモデルにOptionalフィールド3つを追加するだけで後方互換性を維持

## Research Log

### FTS検索での字幕スニペット取得方法
- **Context**: FTS検索がセグメント単位で結果を返すが、マッチした字幕テキストは含まれていない
- **Findings**:
  - 現行の`fts_search_segments`はDISTINCTでセグメントを重複排除しており、個別の字幕行テキストは捨てられている
  - `subtitle_fts`テーブルには`text`カラムがあり、SELECTに追加するだけで取得可能
  - 同一セグメント内で複数行がマッチする場合、GROUP_CONCATで集約するか最初の1行のみ取得するかの選択がある
  - FTS5の`snippet()`関数は trigram tokenizer では使用不可（highlight/snippetはデフォルトtokenizerのみ対応）
  - trigramトークナイザーは3文字未満のクエリではマッチしないため、短いクエリ（1〜2文字）ではFTS検索が機能せずスニペットも生成されない。この場合は`subtitle_lines`テーブルへの`LIKE`フォールバックで字幕検索を行い、スニペットを生成する
- **Implications**: GROUP_CONCATで同一セグメント内のマッチ行を連結し、スニペットとして返すアプローチが適切。短いクエリにはLIKEフォールバックで同等のスニペットを提供する

### ベクトル検索の類似度スコア変換
- **Context**: ベクトル検索のdistanceを人間が理解しやすい類似度に変換する必要がある
- **Findings**:
  - 現行の`vector_search`は`distance`を返却済み（sqlite-vecのコサイン距離）
  - `_merge_results`で既に`max(0, 1.0 - distance)`のスコア変換を実施
  - 同じ変換ロジック（`1.0 - distance`）をパーセンテージ表示に利用可能
- **Implications**: 新たなDB問い合わせは不要。既存のdistance値を変換してSearchResultに設定するだけ

### マッチ種別の追跡方法
- **Context**: `_merge_results`でFTS結果とベクトル結果をマージする際に、各結果の出自を追跡する必要がある
- **Findings**:
  - 現行ロジックでは`seen_segment_ids`で重複を検出しスコアをブーストしているが、マッチ種別は記録していない
  - マージ時にFTS由来かベクトル由来かの情報を中間dictに保持する必要がある
- **Implications**: 中間データ構造にmatch_type, snippet, similarityフィールドを追加し、マージ時に更新する

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| SearchResultモデル拡張 | 既存のSearchResultにOptionalフィールドを追加 | 後方互換性維持、変更最小 | フィールド数増加 | 採用 |
| 別モデル作成 | SearchResultWithReasonのような新モデル | 既存への影響ゼロ | 型の分岐が複雑化 | 不採用 |

## Design Decisions

### Decision: FTS字幕スニペットの取得方法
- **Context**: FTSマッチした字幕テキストをセグメント単位で取得する必要がある
- **Alternatives Considered**:
  1. GROUP_CONCATで同一セグメント内のマッチ行を連結
  2. サブクエリで最初のマッチ行のみ取得
  3. 別クエリで字幕テキストを後から取得
- **Selected Approach**: GROUP_CONCATで連結し、区切り文字「…」で結合
- **Rationale**: 単一クエリで完結し、複数マッチ箇所がある場合にコンテキストが豊富になる
- **Trade-offs**: 文字列が長くなる可能性があるが、CLI側でtruncateすれば良い

### Decision: マッチ種別のEnum定義
- **Context**: マッチ種別を型安全に表現する必要がある
- **Selected Approach**: StrEnumで`keyword` / `semantic` / `hybrid`の3値を定義
- **Rationale**: 既存のSkipReasonと同じパターン（StrEnum）を踏襲

## Risks & Mitigations
- FTS検索クエリの変更でパフォーマンスが低下する可能性 — GROUP_CONCATの結果をLIMITで制限
- スニペットが非常に長くなる可能性 — CLI表示時に最大文字数で切り詰め
