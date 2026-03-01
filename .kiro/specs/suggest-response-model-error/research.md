# Research & Design Decisions

## Summary
- **Feature**: `suggest-response-model-error`
- **Discovery Scope**: Extension（既存バグ修正）
- **Key Findings**:
  - `src/kirinuki/infra/llm.py:86` で `response_model` パラメータを Anthropic SDK の `messages.create()` に渡しているが、これは `instructor` ライブラリ固有の機能であり素の Anthropic SDK では未対応
  - `src/kirinuki/infra/llm_client.py` に確立されたパターン（JSON手動パース + 正規表現コードフェンス除去）が存在する
  - Pydantic の `BaseModel` はレスポンスパース用のバリデーションに引き続き活用可能

## Research Log

### Anthropic SDK の `response_model` サポート状況
- **Context**: `Messages.create() got an unexpected keyword argument 'response_model'` エラーの原因調査
- **Sources Consulted**: `src/kirinuki/infra/llm.py`、`src/kirinuki/infra/llm_client.py`、Anthropic SDK ドキュメント
- **Findings**:
  - `response_model` は `instructor` ライブラリが Anthropic クライアントにパッチする機能
  - 本プロジェクトでは `instructor` は使用しておらず、素の `anthropic` パッケージのみ依存
  - `llm_client.py` では JSON テキストレスポンスを `json.loads()` + Pydantic バリデーションでパースする確立パターンがある
- **Implications**: `instructor` を導入するのではなく、既存パターンに合わせてJSONパースに修正する

### 既存LLMレスポンスパースパターンの分析
- **Context**: `llm_client.py` の実装パターン確認
- **Sources Consulted**: `src/kirinuki/infra/llm_client.py`
- **Findings**:
  - コードフェンス除去: `re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip())` + `re.sub(r"\n?```\s*$", "", raw_text)`
  - JSON パース: `json.loads(raw_text)` で辞書リストにデコード
  - エラーハンドリング: `JSONDecodeError` をキャッチして空リスト返却 + 警告ログ
  - モデル変換: 辞書からドメインオブジェクトを手動構築
- **Implications**: `llm.py` でも同一パターンを適用。追加で Pydantic `model_validate` を使いバリデーションも行える

## Design Decisions

### Decision: JSONパースアプローチの選択
- **Context**: `response_model` エラーの修正方法
- **Alternatives Considered**:
  1. `instructor` ライブラリを導入して `response_model` を正式にサポート
  2. 既存パターンに合わせてJSON手動パース + Pydanticバリデーションに修正
- **Selected Approach**: Option 2（JSON手動パース）
- **Rationale**: プロジェクト全体で確立済みのパターンと一致。新しい依存を追加する必要がない。`llm_client.py` と統一的な実装になる
- **Trade-offs**: instructor の型安全なレスポンス取得は失われるが、Pydantic バリデーションで同等のチェックは可能
- **Follow-up**: プロンプトにJSON出力形式の明示指示を追加する必要あり

## Risks & Mitigations
- LLMがJSON形式以外で応答するリスク → プロンプトで明示指示 + コードフェンス除去 + `JSONDecodeError` ハンドリング
- バリデーションエラーのリスク → `SegmentEvaluation` Pydantic モデルでランタイムチェック

## References
- `src/kirinuki/infra/llm_client.py` — 確立されたJSONパースパターン
- `src/kirinuki/infra/llm.py` — バグのある現行実装
