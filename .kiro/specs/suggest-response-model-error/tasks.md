# Implementation Plan

- [x] 1. evaluate_segments メソッドを JSON 手動パース方式に修正する
- [x] 1.1 評価プロンプトに JSON 出力形式の明示指示を追加する
  - 評価結果を `evaluations` キーを持つ JSON オブジェクト形式で返すよう、プロンプト末尾に出力フォーマットの指示を追加する
  - 各評価要素のスキーマ（`segment_id`, `score`, `summary`, `appeal`）をプロンプト内で明示する
  - 他のテキストを含めずJSON のみを出力するよう指示する
  - _Requirements: 2.2_

- [x] 1.2 response_model を除去し、テキストレスポンスの JSON パースとバリデーションを実装する
  - `messages.create()` から `response_model` パラメータを削除する
  - テキストレスポンスからコードフェンス（```json ... ```）を正規表現で除去する（既存 `llm_client.py` と同一パターン）
  - `json.loads()` で JSON をデコードし、`EvaluationResponse.model_validate()` で Pydantic バリデーションを行う
  - バリデーション済みの結果を `SegmentRecommendation` リストに変換する
  - 必要な import（`json`, `re`, `logging`）を追加する
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.3_

- [x] 1.3 JSON パースエラーおよびバリデーションエラーのハンドリングを追加する
  - `json.JSONDecodeError` をキャッチし、空リストを返却して警告ログを出力する
  - Pydantic `ValidationError` をキャッチし、空リストを返却して警告ログを出力する
  - ログメッセージにはレスポンスの先頭200文字を含め、デバッグを容易にする
  - _Requirements: 1.4_

- [x] 2. ユニットテストを追加する
- [x] 2.1 正常系テスト: JSON レスポンスの正常パースと変換を検証する
  - 有効な JSON レスポンスが `SegmentRecommendation` リストに正しく変換されることを検証する
  - `messages.create()` が `response_model` パラメータなしで呼び出されることを検証する
  - _Requirements: 1.1, 1.2_

- [x] 2.2 (P) コードフェンスおよびエラー系テスト: 各種レスポンス形式を検証する
  - コードフェンス（```json ... ```）で囲まれた JSON が正しくパースされることを検証する
  - 不正な JSON レスポンス時に空リストが返却され、警告ログが出力されることを検証する
  - スキーマ不一致（例: score が範囲外）時に空リストが返却されることを検証する
  - _Requirements: 1.3, 1.4_
