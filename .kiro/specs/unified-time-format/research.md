# Research & Design Decisions

## Summary
- **Feature**: `unified-time-format`
- **Discovery Scope**: Extension（既存システムの表示フォーマット修正）
- **Key Findings**:
  - 時間範囲の区切り文字が3種類存在（` - `、`〜`、`-`）、clipコマンド入力のみ`-`（スペースなし）
  - 変更対象は4箇所（search, segments, suggest, clip出力）で全て表示層に閉じる
  - `format_time`関数自体は変更不要、範囲結合ロジックの一元化が最適解

## Research Log

### 現状の時間範囲フォーマット差異
- **Context**: clipコマンドへのコピペ運用で手動整形が必要という課題
- **Sources Consulted**: ソースコード直接確認
- **Findings**:
  - `src/kirinuki/cli/main.py` search: `f"{start_str} - {end_str}"` (L206)
  - `src/kirinuki/cli/main.py` segments: `f"  {start_str} - {end_str}"` (L230)
  - `src/kirinuki/core/formatter.py` suggest: `f"  [{rec.score}/10] {start_str} 〜 {end_str}"` (L53)
  - `src/kirinuki/cli/clip.py` clip出力: `f"  {outcome.output_path} ({start_str} - {end_str})"` (L91, L100)
- **Implications**: 全箇所で`format_time`を個別に2回呼び出してから文字列結合しており、結合ロジックが分散している

### clipコマンドの入力パーサー互換性
- **Context**: 出力フォーマットがパーサーと互換であることの確認
- **Sources Consulted**: `src/kirinuki/core/clip_utils.py` `parse_time_str()`
- **Findings**:
  - `M:SS`、`H:MM:SS`、生float秒を受容
  - 範囲区切りは最後の`-`で分割（`rsplit("-", 1)`）
  - `format_time`の出力（`M:SS` / `H:MM:SS`）はパーサーが直接受容可能
- **Implications**: `format_time`の出力をそのまま`-`で結合すれば、clipコマンドの入力として有効

## Design Decisions

### Decision: `format_time_range` ヘルパー関数の導入
- **Context**: 4箇所で個別に`format_time(start) + 区切り + format_time(end)`を行っている
- **Alternatives Considered**:
  1. 各箇所で区切り文字を`-`に直接変更（関数追加なし）
  2. `format_time_range`ヘルパー関数を`formatter.py`に追加し、全箇所で利用
- **Selected Approach**: Option 2 — ヘルパー関数導入
- **Rationale**: フォーマットロジックの一元化により、将来の変更時に1箇所の修正で済む。既存`format_time`は変更せず影響範囲を最小化
- **Trade-offs**: 関数1つの追加のみで、複雑性の増加は無視できる
- **Follow-up**: テストで`format_time_range`の出力がclipパーサーで正しくパースされることを検証

## Risks & Mitigations
- 既存テストが` - `や`〜`区切りを期待している可能性 → テスト修正が必要
- ユーザーが旧フォーマットに依存したスクリプトを持つ可能性 → 影響は表示のみで軽微
