# Research & Design Decisions

---
**Purpose**: youtube-live-clipperの技術設計に向けたディスカバリー調査結果
---

## Summary
- **Feature**: `youtube-live-clipper`
- **Discovery Scope**: New Feature（グリーンフィールド）
- **Key Findings**:
  - yt-dlpの`extract_flat`モードでチャンネル全動画のID一覧を高速取得可能。差分同期は自前のID比較で実現
  - SQLite FTS5の`trigram`トークナイザーが日本語に対応（外部依存不要）
  - sqlite-vecでFTS5と同一DBファイルにベクトルインデックスを同居可能
  - Claude Haiku 4.5で3時間配信の字幕セグメンテーションが約$0.07〜0.13/回

## Research Log

### yt-dlp Python APIによるチャンネル同期
- **Context**: チャンネル全動画の字幕を差分同期する方法
- **Sources**: yt-dlp GitHub、DeepWiki、yt-dlp issues
- **Findings**:
  - `extract_flat=True`で動画IDリストを高速取得（メタデータのみ、DLなし）
  - `skip_download=True` + `writesubtitles=True` + `writeautomaticsub=True`で字幕のみ取得
  - `json3`形式が最適（`tStartMs`, `dDurationMs`, `segs[].utf8`の構造化データ）
  - Cookie認証: `cookiefile`パラメータでNetscape形式のCookieファイルを渡す
  - `cookiesfrombrowser`: 4要素タプル `('firefox', None, None, None)` で指定
  - `upload_date`はflat extractionでは近似値のみ。正確な日時にはfull extractionが必要
- **Implications**:
  - 同期フロー: flat extraction → DB比較で新規IDを特定 → 新規動画のみfull extraction + 字幕取得
  - `break_on_existing`は使わず、自前のID管理で差分検出（flat extractionの方が高速）

### SQLite FTS5と日本語全文検索
- **Context**: 字幕テキストのキーワード検索
- **Sources**: SQLite公式ドキュメント、日本語FTS実装事例
- **Findings**:
  - デフォルトトークナイザー（unicode61）は空白区切り前提で日本語非対応
  - `trigram`トークナイザー（SQLite 3.34.0+）が日本語に対応。3文字スライディングウィンドウで部分一致検索
  - ICUトークナイザーはPython標準sqlite3では利用不可（コンパイルフラグが必要）
  - trigramはインデックスサイズが大きくなるが、10万セグメント規模なら問題なし
- **Implications**: FTS5 + trigramで外部依存なしに日本語キーワード検索を実現

### ベクトル検索とエンベディング
- **Context**: 意味検索（セマンティックサーチ）の実現方法
- **Sources**: sqlite-vec GitHub、ChromaDB、HuggingFace、Anthropic docs、Voyage AI docs
- **Findings**:
  - **sqlite-vec** (v0.1.6): `pip install sqlite-vec`でインストール、Python標準sqlite3と互換。同一DBファイルにベクトルテーブルを同居可能
  - ChromaDBは依存が重く、別ファイル管理が必要
  - **Anthropicはエンベディング非提供**
  - ローカル: `cl-nagoya/ruri-v3-310m`が日本語JMTEB最高スコア（77.24）。768次元、8192トークン。ただし~1.2GBのモデルDLが必要
  - API: Voyage AI `voyage-3.5-lite`（$0.02/MTok、200M無料枠）、OpenAI `text-embedding-3-small`（$0.02/MTok）
- **Implications**: sqlite-vecを採用。エンベディング生成はインターフェースで抽象化し、初期実装ではVoyage AIまたはOpenAI APIで軽量に開始。ローカルモデルは将来オプション

### Claude APIによる話題セグメンテーション
- **Context**: 長時間配信の字幕を話題ごとに分割する方法
- **Sources**: Anthropic公式ドキュメント、pricing page
- **Findings**:
  - 3時間配信 ≒ 6万文字 ≒ 12万トークン。標準200Kコンテキストに収まる
  - Structured Outputs（GA）でJSON出力を保証。Pydantic統合あり
  - Haiku 4.5: 入力$1/MTok、出力$5/MTok → 3時間配信1本あたり約$0.13
  - Batch API: 50%割引（$0.07/本）、結果は24時間以内
  - Prompt Caching: システムプロンプトのキャッシュで入力コスト90%削減
  - 4時間超の配信は45分チャンク+5分オーバーラップで分割処理
- **Implications**: Haiku 4.5をデフォルトモデルに。初回大量同期はBatch API検討。通常の差分同期は同期的API呼び出し

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| レイヤードアーキテクチャ | CLI → Core → Infra の3層 | シンプル、テスト容易、steering準拠 | 層間の依存が固定的 | steering既定パターン |
| Hexagonal | Ports & Adapters | 外部依存の差し替えが容易 | CLIツールには過剰な抽象化 | インフラ層の設計思想は取り入れる |

**選択**: レイヤードアーキテクチャをベースに、インフラ層はProtocol（ポート）で抽象化するハイブリッド

## Design Decisions

### Decision: 差分同期の方式
- **Context**: チャンネルの新規動画を効率的に検出する方法
- **Alternatives Considered**:
  1. yt-dlpの`break_on_existing`オプション
  2. 自前のID比較（flat extraction → DB比較）
- **Selected Approach**: 自前のID比較
- **Rationale**: flat extractionが最速。全ID取得→DB比較で新規を特定→新規のみfull extraction。yt-dlpのarchiveファイル管理は不要
- **Trade-offs**: 全IDを毎回取得するが、flat extractionなのでコストは低い

### Decision: エンベディング戦略
- **Context**: 意味検索のためのベクトル生成方法
- **Alternatives Considered**:
  1. ローカルモデル（ruri-v3-310m）— 日本語最高品質、1.2GB DL
  2. Voyage AI API — 軽量、200M無料枠
  3. OpenAI API — 汎用的、安価
- **Selected Approach**: EmbeddingProviderインターフェースで抽象化。デフォルトはOpenAI `text-embedding-3-small`
- **Rationale**: ローカルモデルは初回DLが重い。APIは軽量で始められ、セグメント要約テキスト（短文）のみベクトル化するのでコストも低い。インターフェース抽象化で後から切り替え可能
- **Follow-up**: ローカルモデル対応は将来オプションとして設計に含める

### Decision: 字幕フォーマット
- **Context**: yt-dlpから取得する字幕のフォーマット選択
- **Selected Approach**: `json3`形式
- **Rationale**: 構造化データ（開始時刻、持続時間、テキスト）がJSON形式で取得でき、パース不要。vtt/srtはテキスト解析が必要

### Decision: セグメンテーション実行タイミング
- **Context**: LLMによる話題分割をいつ実行するか
- **Selected Approach**: 同期時に即座実行（字幕取得→セグメンテーション→インデックス登録をパイプライン処理）
- **Rationale**: 検索時にセグメントが必要。同期時は通常1〜数本なのでレイテンシーは許容範囲
- **Trade-offs**: 初回大量同期時は時間がかかる。将来的にBatch APIで最適化可能

## Risks & Mitigations
- yt-dlpのAPI安定性: yt-dlpはCLIツールが主目的でPython APIは非公式。マイナーバージョンで破壊的変更の可能性 → インフラ層で薄くラップし、影響範囲を限定
- Cookie認証の有効期限: Cookieは定期的に失効する → エラー時にCookie更新を促すメッセージ表示
- LLMコスト: 初回同期で大量の動画を処理すると高額になる可能性 → 同期対象の制限オプション、Batch API対応
- sqlite-vecのpre-v1ステータス: API変更の可能性 → インフラ層で抽象化、テストで変更検知

## References
- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp) — Python APIドキュメント、オプション一覧
- [SQLite FTS5](https://sqlite.org/fts5.html) — trigramトークナイザー仕様
- [sqlite-vec](https://github.com/asg017/sqlite-vec) — ベクトル検索拡張
- [Anthropic API Docs](https://docs.anthropic.com/) — Structured Outputs、Batch API、料金
- [cl-nagoya/ruri-v3-310m](https://huggingface.co/cl-nagoya/ruri-v3-310m) — 日本語エンベディングモデル
- [Voyage AI](https://docs.voyageai.com/) — エンベディングAPI
