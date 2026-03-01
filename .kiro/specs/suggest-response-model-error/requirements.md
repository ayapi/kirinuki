# Requirements Document

## Introduction

`kirinuki suggest` コマンド実行時に、`Messages.create() got an unexpected keyword argument 'response_model'` エラーが発生する。
原因は `src/kirinuki/infra/llm.py` の `evaluate_segments` メソッドが Anthropic SDK の `messages.create()` に `response_model` パラメータを渡しているが、
これは `instructor` ライブラリでパッチされたクライアントでのみ有効なパラメータであり、素の Anthropic SDK では未対応であること。

既存の `src/kirinuki/infra/llm_client.py` では JSON レスポンスを手動パースするパターンが確立されているため、
`llm.py` でも同様のアプローチ（JSON パース + Pydantic バリデーション）に修正する。

## Requirements

### Requirement 1: LLM評価レスポンスのJSONパース

**Objective:** ユーザーとして、`kirinuki suggest` コマンドを実行した際に、セグメント評価がエラーなく完了する機能が欲しい。これにより、切り抜き候補の推薦を正常に受け取れるようにするため。

#### Acceptance Criteria

1. When `evaluate_segments` メソッドが呼び出された場合, the LLMClient shall Anthropic SDK の `messages.create()` を `response_model` パラメータなしで呼び出し、テキストレスポンスをJSONとしてパースする
2. When LLMレスポンスが有効なJSON配列を含む場合, the LLMClient shall 各要素を `SegmentEvaluation` Pydanticモデルでバリデーションし、`SegmentRecommendation` のリストに変換する
3. If LLMレスポンスがmarkdownコードフェンス（```json ... ```）で囲まれている場合, then the LLMClient shall コードフェンスを除去してからJSONパースを行う
4. If LLMレスポンスが不正なJSONを返した場合, then the LLMClient shall 空のリストを返し、ログに警告メッセージを出力する

### Requirement 2: 既存パターンとの一貫性

**Objective:** 開発者として、LLMレスポンス処理のパターンがプロジェクト内で統一されていてほしい。これにより、コードの保守性と可読性を維持するため。

#### Acceptance Criteria

1. The LLMClient shall `llm_client.py` と同様のJSON手動パース+正規表現によるコードフェンス除去パターンを使用する
2. The LLMClient shall 評価プロンプトでJSON配列形式の出力を明示的に指示する
3. The LLMClient shall `instructor` ライブラリへの依存を持たない
