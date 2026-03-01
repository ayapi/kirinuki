# Research & Design Decisions

## Summary
- **Feature**: `sync-format-unavailable`
- **Discovery Scope**: Extension（既存システムの修正）
- **Key Findings**:
  - yt-dlpの`ignore_no_formats_error`オプションで、フォーマット選択エラーを抑制しつつ情報抽出を続行できる
  - `_base_opts()`は情報抽出系メソッド専用。`download_video()`は独自のopts辞書を使用するため影響を受けない
  - 修正は`_base_opts()`への1行追加で完結する。エラー分類の変更は不要

## Research Log

### yt-dlpの`ignore_no_formats_error`オプション
- **Context**: `skip_download=True`でもyt-dlpがフォーマット選択を実行し、マッチするフォーマットがない場合にエラーを発生させる
- **Sources Consulted**: yt-dlp ソースコード（`.venv/Lib/site-packages/yt_dlp/YoutubeDL.py`）
- **Findings**:
  - `YoutubeDL.py`の`process_video_result()`内で、`ignore_no_formats_error`がTrueの場合、フォーマットが見つからなくても`ExtractorError`を発生させず処理を続行する
  - このオプションはCLIの`--ignore-no-formats-error`に対応する公式オプション
  - メタデータ・字幕の抽出はフォーマット選択より前に完了するため、フォーマットエラーを無視すれば情報は正常に取得できる
- **Implications**: `_base_opts()`に`"ignore_no_formats_error": True`を追加するだけで根本原因を解消できる

### `_base_opts()`のスコープ分析
- **Context**: `_base_opts()`変更が`download_video()`に影響しないことを確認する
- **Findings**:
  - `_base_opts()`を使用するメソッド: `fetch_video_metadata()`, `fetch_subtitle()`, `list_channel_video_ids()`, `resolve_channel_name()`
  - `download_video()`は`_base_opts()`を**使用しない**。独自のopts辞書を構築している（ytdlp_client.py:201-206）
  - よって`_base_opts()`の変更は`download_video()`に一切影響しない
- **Implications**: Requirement 3（clip機能への非影響）は設計上自然に満たされる

### エラー分類の必要性再評価
- **Context**: Requirement 2でフォーマット不可と動画利用不可の区別を求めている
- **Findings**:
  - `ignore_no_formats_error=True`を設定すると、フォーマット不可エラー自体が発生しなくなる
  - yt-dlpはフォーマットエラーをスキップし、メタデータ・字幕の抽出を正常に完了する
  - 「真に利用不可」（削除・非公開等）の場合は別のエラー（`Video unavailable`等）が引き続き発生する
  - エラー分類の明示的な追加は不要。既存のエラーハンドリングが正しく機能する
- **Implications**: Requirement 2はRequirement 1の修正により暗黙的に満たされる

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| `_base_opts()`に`ignore_no_formats_error`追加 | 情報抽出用ベースオプションにフォーマットエラー抑制を追加 | 最小変更、根本原因を直接解決、`download_video()`に影響なし | なし | 採用 |
| メソッド個別に`ignore_no_formats_error`追加 | `fetch_video_metadata()`と`fetch_subtitle()`のみに追加 | 明示的 | 冗長、`_base_opts()`は既に情報抽出専用 | 不採用 |
| エラーメッセージでフォーマットエラーを判定し特別処理 | `_is_auth_error()`と同様のパターン | エラー種別が明確 | 過剰設計、根本原因を解決しない | 不採用 |

## Design Decisions

### Decision: `_base_opts()`への`ignore_no_formats_error`追加
- **Context**: sync（情報抽出のみ）でフォーマット選択エラーが発生し、字幕・メタデータが取得できない
- **Alternatives Considered**:
  1. `_base_opts()`に追加 — 全情報抽出メソッドに一括適用
  2. 各メソッドに個別追加 — 影響範囲を限定
  3. エラーハンドリングで吸収 — エラー発生後にリカバリ
- **Selected Approach**: Option 1 — `_base_opts()`に`"ignore_no_formats_error": True`を追加
- **Rationale**: `_base_opts()`は`skip_download=True`を前提とした情報抽出専用。フォーマット選択は不要なため、エラー抑制は論理的に正しい。`download_video()`は独自optsを使うため影響なし
- **Trade-offs**: 将来`_base_opts()`を動画DLに流用した場合にフォーマットエラーが検出されないリスクがあるが、現状のアーキテクチャでは発生しない
- **Follow-up**: テストで`download_video()`のフォーマットエラー動作が維持されることを検証

## Risks & Mitigations
- `_base_opts()`のスコープ拡大リスク — `download_video()`が将来`_base_opts()`を使うようリファクタリングされた場合、フォーマットエラーが隠蔽される。コメントでopts使い分けの意図を明記することで軽減

## References
- yt-dlp公式ドキュメント: `ignore_no_formats_error`オプション
- yt-dlp ソースコード `YoutubeDL.py`: フォーマット選択ロジック
