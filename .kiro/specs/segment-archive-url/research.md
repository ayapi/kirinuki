# Research & Design Decisions

## Summary
- **Feature**: `segment-archive-url`
- **Discovery Scope**: Extension（既存システムへの軽量な機能追加）
- **Key Findings**:
  - URL生成関数が2箇所に重複して存在し、インターフェースも異なる
  - `clip_utils.py` がURL関連ユーティリティの自然な配置先
  - `segments` コマンドは `video_id` を引数として受け取っており、URLに必要な情報はすべて揃っている

## Research Log

### URL生成ロジックの現状分析
- **Context**: 要件2（共通化）を満たすため、現在の重複箇所を調査
- **Sources Consulted**: `search_service.py:83-85`, `formatter.py:23-25`, `clip_utils.py`
- **Findings**:
  - `SearchService._generate_youtube_url(video_id: str, start_ms: int)` — ミリ秒を受け取り `// 1000` で秒に変換
  - `RecommendationFormatter.build_youtube_url(video_id: str, start_seconds: int)` — 秒を受け取る（変換なし）
  - `clip_utils.py` にはURL解析（`extract_video_id`）は存在するがURL生成はない
- **Implications**: 統一関数はミリ秒を受け取るインターフェースにすべき（ドメインモデル `Segment.start_ms` がミリ秒であるため）。`suggest` の `SegmentRecommendation.start_time` は秒単位なので呼び出し側で変換する

### segments コマンドの出力形式
- **Context**: 要件1を満たすため、現在の出力形式と追加すべき行を検討
- **Sources Consulted**: `main.py:154-172`
- **Findings**:
  - 現在の出力: `  MM:SS - MM:SS | 要約` の1行のみ
  - `search` コマンドは要約行の下にURL行を追加する形式
  - `video_id` はコマンド引数として利用可能
- **Implications**: `search` と同様にセグメント情報行の下にURL行を追加するのが一貫性あるUX

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| clip_utils.py に共通関数追加 | URL解析と生成を同一モジュールに集約 | 関連機能の凝集度が高い、既存パターンに沿う | なし | **採用** |
| 新規 url_utils.py 作成 | URL専用モジュール | 分離は明確 | 過度な分割、既存 clip_utils.py と重複 | 却下 |
| models/domain.py に Segment メソッド追加 | Segment モデルにURL生成メソッド | データとロジックの近接 | Pydantic BaseModel にロジックを入れるのはプロジェクト規約に反する | 却下 |

## Design Decisions

### Decision: URL生成関数の配置先
- **Context**: 重複するURL生成ロジックを一箇所に統合する必要がある
- **Alternatives Considered**:
  1. `clip_utils.py` に追加 — URL解析 (`extract_video_id`) と対になる生成関数を同じモジュールに
  2. `formatter.py` の既存関数を共通化 — 推薦専用フォーマッターに他コマンドが依存してしまう
  3. 新規モジュール作成 — 過度な分割
- **Selected Approach**: `clip_utils.py` に `build_youtube_url(video_id: str, start_ms: int) -> str` を追加
- **Rationale**: URL解析と生成は同じドメイン。コア層ユーティリティとして全コマンドから参照可能
- **Trade-offs**: `formatter.py` の `build_youtube_url` は削除し呼び出し元を変更する必要がある
- **Follow-up**: 既存テストが共通関数経由で動作することを確認

### Decision: 共通関数のインターフェース
- **Context**: 既存2関数のインターフェースが異なる（ミリ秒 vs 秒）
- **Selected Approach**: `start_ms: int`（ミリ秒）を受け取る
- **Rationale**: ドメインモデル（`Segment.start_ms`, `SearchResult.start_time_ms`）がミリ秒を使用。`suggest` の `SegmentRecommendation.start_time`（秒）は呼び出し側で `int(start_time * 1000)` に変換

## Risks & Mitigations
- **リスク1**: `formatter.py` のインターフェース変更による `suggest` の出力変化 — 変換式のテストで担保
- **リスク2**: ミリ秒→秒変換での丸め誤差 — 整数除算 `// 1000` で一貫して切り捨て（既存動作と同一）

## References
- YouTube URL `&t=` パラメータ: 秒単位の整数値を受け付ける（`&t=123` で2分3秒地点から再生）
