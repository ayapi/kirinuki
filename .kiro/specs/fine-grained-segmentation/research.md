# Research & Design Decisions

## Summary
- **Feature**: `fine-grained-segmentation`
- **Discovery Scope**: Extension（既存セグメンテーション機能の粒度改善）
- **Key Findings**:
  - 既存の「1分未満統合」「明確な話題変化のみ分割」方針が10〜30分超のセグメント生成の原因
  - LLMプロンプト改善だけでは長大セグメントを完全に排除できず、再分割メカニズムが必要
  - チャンクサイズ縮小（45→20分）によりLLMの分析精度が向上する

## Research Log

### 既存セグメンテーションの課題分析
- **Context**: ユーザーから「セグメントが大きすぎて特定の話題が見つからない」との報告
- **Findings**:
  - SYSTEM_PROMPTに「短すぎるセグメント（1分未満）は前後と統合してください」の指示が存在
  - 「話題の切り替わりが明確な箇所で分割」という基準が大分類レベルの分割に留まる原因
  - CHUNK_MINUTES=45は1チャンクあたりの情報量が多く、LLMの細粒度分析を阻害
- **Implications**: プロンプト、チャンクサイズ、後処理の3箇所に同時に変更が必要

### 再分割戦略の検討
- **Context**: プロンプト改善後も一部セグメントが長大になる可能性への対策
- **Findings**:
  - 再帰的な再分割は無限ループのリスクがあり、1パスのみが安全
  - 親セグメントのsummaryをコンテキストとして注入することで分割品質が向上
  - 再分割結果が1件以下の場合は元セグメントを保持するフォールバックが必要
- **Implications**: `_resplit_oversized`は1パス設計、フォールバック付き

### 再セグメンテーション機能の必要性
- **Context**: 既存データに新しいセグメンテーション設定を適用する手段が必要
- **Findings**:
  - segment_vectorsはsegmentsへのFK参照があるため、削除順序が重要
  - 字幕データはDB内に保存済みのため、YouTube APIの再呼び出しは不要
- **Implications**: `delete_segments`でvectors→segments順に削除、`resegment_video`でDB内字幕を再利用

## Design Decisions

### Decision: チャンクサイズの縮小
- **Context**: 長時間配信（4時間超）のLLM分析精度を改善
- **Alternatives Considered**:
  1. 45分チャンクのまま維持 — プロンプト改善のみに頼る
  2. 20分チャンクに縮小 — LLMの注意力をより狭い範囲に集中
  3. 10分チャンクに縮小 — さらに細かいがAPI呼び出し回数が増大
- **Selected Approach**: 20分チャンク + 3分オーバーラップ
- **Rationale**: API呼び出し回数とLLM分析精度のバランス。オーバーラップも5→3分に縮小し、重複排除の負荷を軽減
- **Trade-offs**: APIコスト増加（チャンク数約2倍）vs セグメント品質向上

### Decision: 再分割の1パス制限
- **Context**: max_segment_ms超のセグメントの再分割深度
- **Alternatives Considered**:
  1. 再帰的に再分割 — 完全に最大長以下にできるが無限ループリスク
  2. 1パスのみ — 再分割後も超過する場合はそのまま保持
- **Selected Approach**: 1パスのみ
- **Rationale**: 安全性優先。再帰的分割は品質劣化リスクもあり、1パスで大半のケースをカバーできる
- **Trade-offs**: 極端に長いセグメントが残る可能性あり vs 実装の安全性・単純性

### Decision: 意味ベースフィルタ
- **Context**: セグメント最小長制約を撤廃した際のノイズ対策
- **Alternatives Considered**:
  1. 時間ベース統合を維持 — 従来の1分未満統合
  2. 完全撤廃（統合なし） — フィラーのみの区間もセグメント化
  3. 意味ベースフィルタ — フィラーは隣接に含めるがそれ以外は自由長
- **Selected Approach**: 意味ベースフィルタ（LLMプロンプトで指示）
- **Rationale**: フィラー・相槌のみの区間を独立セグメントにしても検索価値がないため、LLMの判断に委ねる
- **Trade-offs**: LLMの判断精度に依存 vs 時間ベース統合の情報損失回避

## Risks & Mitigations
- LLMのプロンプト変更による既存セグメンテーション品質の変動 — resegmentコマンドで全動画の再セグメンテーションが可能
- APIコスト増加（チャンクサイズ縮小＋再分割） — max_segment_msのデフォルト値を調整可能
- 再分割時のLLM応答がJSON不正の場合 — 元セグメントを保持するフォールバック

## References
- Anthropic Claude API — プロンプト設計のベストプラクティス
- 既存コードベース `src/kirinuki/core/segmentation_service.py` — チャンク分割・重複排除ロジック
