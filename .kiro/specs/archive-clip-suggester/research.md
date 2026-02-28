# Research & Design Decisions

---
**Purpose**: archive-clip-suggesterの技術設計に向けたディスカバリー調査結果
---

## Summary
- **Feature**: `archive-clip-suggester`
- **Discovery Scope**: Extension（`youtube-live-clipper` の既存基盤を拡張）
- **Key Findings**:
  - 既存のClaude API基盤（`infra/llm.py`）をそのまま再利用し、Structured Outputsで切り抜き適性スコア+魅力紹介テキストを一括生成可能
  - 動画単位のバッチ評価（1動画の全セグメントを1回のAPI呼び出しで評価）がコスト・品質両面で最適
  - 既存DBスキーマに推薦スコアキャッシュ用テーブルを追加することで、同一セグメントの再評価を回避可能

## Research Log

### LLMによる切り抜き適性評価の設計
- **Context**: セグメントの「切り抜き向き度合い」をどうLLMに評価させるか
- **Sources**: youtube-live-clipper research.md（Claude API調査）、Anthropic Structured Outputs docs
- **Findings**:
  - 1動画あたりのセグメント数は通常10〜30程度。全セグメントの要約テキストを1回のプロンプトに含めてバッチ評価が可能
  - Structured Outputsで `list[SegmentRecommendation]` 形式のJSON出力を保証
  - 個別評価（セグメントごと1API呼び出し）は比較文脈が失われ、スコアの一貫性が低下
  - バッチ評価では動画全体の流れを踏まえた相対評価が可能
  - Haiku 4.5: 入力約3,000〜5,000トークン/動画（セグメント要約一覧）、出力約1,000〜2,000トークン → 1動画あたり約$0.01未満
- **Implications**: 動画単位バッチ評価を採用。コストは3動画で$0.03未満。比較評価により品質も向上

### 推薦スコアのキャッシュ戦略
- **Context**: 同じセグメントを再評価しないためのキャッシュ
- **Sources**: 既存DBスキーマ設計（youtube-live-clipper design想定）
- **Findings**:
  - セグメントはsync時に確定し、以後変更されない → スコアは永続キャッシュ可能
  - 評価基準（プロンプト）のバージョン管理が必要。プロンプト変更時にキャッシュ無効化
  - SQLiteの既存テーブルに推薦スコアカラムを追加する方法と、別テーブルにする方法
  - 別テーブル方式の方が責務分離が明確。セグメントテーブルの変更不要
- **Implications**: `segment_recommendations`テーブルを新設。`prompt_version`カラムで無効化判定

### 既存コンポーネントとの統合ポイント
- **Context**: youtube-live-clipper基盤との接続方法
- **Sources**: steering文書（structure.md, tech.md）、youtube-live-clipper仕様
- **Findings**:
  - `infra/db.py`: 動画メタデータ・セグメントのクエリ → そのまま再利用
  - `infra/llm.py`: Claude API呼び出し → 評価用プロンプトを追加
  - `models/segment.py`: セグメントモデル → 拡張不要、新たに推薦モデルを追加
  - CLI層: 既存のサブコマンド体系に `suggest` を追加
- **Implications**: 新規ファイルは最小限（CLI 1ファイル + Core 1ファイル + Model 1ファイル）。インフラ層は既存のまま

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 既存レイヤードに統合 | CLI→Core→Infra の既存3層に自然に追加 | 一貫性、低コスト、学習不要 | 特になし | steering準拠、推奨 |

**選択**: 既存レイヤードアーキテクチャにそのまま統合

## Design Decisions

### Decision: セグメント評価のバッチ粒度
- **Context**: LLMにセグメントを評価させる際の粒度
- **Alternatives Considered**:
  1. セグメント単体 — 1セグメント1API呼び出し
  2. 動画単位 — 1動画の全セグメントを1回で評価
  3. 全動画一括 — 全対象動画のセグメントを1回で
- **Selected Approach**: 動画単位バッチ評価
- **Rationale**: 動画内の文脈を活かした比較評価が可能。トークン数は1動画あたり数千で十分収まる。全動画一括はコンテキストが大きくなりすぎる
- **Trade-offs**: 3動画なら3回のAPI呼び出しが必要だが、並列実行可能

### Decision: 推薦結果のキャッシュ
- **Context**: 同一セグメントの再評価回避
- **Selected Approach**: `segment_recommendations`テーブルで永続キャッシュ + `prompt_version`で無効化管理
- **Rationale**: セグメントは不変データなのでスコアも安定。プロンプト改善時のみ再評価
- **Trade-offs**: DB容量は微増するが無視できるレベル

### Decision: 魅力紹介テキストの生成タイミング
- **Context**: 各推薦候補の「なぜ切り抜きに向いているか」のテキストをいつ生成するか
- **Selected Approach**: スコア評価と同時にLLMに生成させる（1回のAPI呼び出しで score + summary + appeal を一括取得）
- **Rationale**: 追加のAPI呼び出し不要。評価の根拠をそのまま言語化できる

## Risks & Mitigations
- LLM評価の一貫性: 同じセグメントでも異なるスコアが出る可能性 → キャッシュで初回評価を固定、temperature=0で再現性向上
- スコアのインフレ/デフレ: LLMがスコアを偏らせる可能性 → プロンプトで具体的なスコア基準を明示、例示を含める
- API障害時の振る舞い: Claude API不通時 → キャッシュ済みスコアがあればそれを返す、なければエラーメッセージ

## References
- youtube-live-clipper research.md — 基盤技術の調査結果（yt-dlp, SQLite FTS5, sqlite-vec, Claude API）
- [Anthropic Structured Outputs](https://docs.anthropic.com/) — JSON出力保証
