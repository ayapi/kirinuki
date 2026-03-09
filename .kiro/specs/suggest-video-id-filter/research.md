# Research & Design Decisions

## Summary
- **Feature**: `suggest-video-id-filter`
- **Discovery Scope**: Extension（既存`suggest`コマンドへのオプション追加）
- **Key Findings**:
  - `search`コマンドに`--video-id`（`multiple=True`）の実装パターンが既に存在し、そのまま踏襲可能
  - `DatabaseClient`（`infra/db.py`）と`Database`（`infra/database.py`）の2つのDBクライアントが存在。`suggest`は前者を使用。`validate_video_ids`は後者にのみ存在
  - `SuggestService`はチャンネルID+count方式で動画を取得するが、video_ids指定時はチャンネルIDの事前解決が不要になる可能性あり

## Research Log

### 既存の--video-idパターン分析
- **Context**: `search`コマンドの`--video-id`実装パターンを踏襲するため調査
- **Sources Consulted**: `cli/main.py:193`, `core/search_service.py:18-46`, `infra/database.py:533-548`
- **Findings**:
  - CLIレベルで`@click.option("--video-id", multiple=True, default=())`として定義
  - コアサービスレベルで`video_ids: list[str] | None = None`としてオプショナル引数
  - バリデーションは`Database.validate_video_ids()`で(existing, missing)タプルを返す
  - missing IDは警告としてユーザーに通知、existing IDのみで処理続行
  - 全ID不在時は空結果を返す（エラー終了ではない）
- **Implications**: `suggest`でも同じパターンを適用可能。ただし`suggest`は`DatabaseClient`を使用するため、`validate_video_ids`相当のメソッドを追加するか、取得時にバリデーションを兼ねる設計が必要

### DatabaseClient vs Database の使い分け
- **Context**: `suggest`は`DatabaseClient`（`infra/db.py`）を使用し、`search`は`Database`（`infra/database.py`）を使用
- **Findings**:
  - `DatabaseClient`はsuggest専用の軽量クライアント（get_latest_videos, get_segments_for_video, get/save_recommendations, channel_exists）
  - `Database`は汎用的なDBアクセス層（validate_video_idsを含む）
  - `DatabaseClient`に`get_videos_by_ids`メソッドを追加すれば、video_idsの取得とバリデーションを1ステップで行える
- **Implications**: `DatabaseClient`にメソッド追加がシンプル。`get_latest_videos`と同じ返り値形式`list[dict[str, str]]`で一貫性を維持

### チャンネルID要否の検討
- **Context**: `--video-id`指定時にチャンネルIDの指定が必要かどうか
- **Findings**:
  - 現在の`suggest`コマンドは`CHANNEL`引数が必須（省略時は自動選択）
  - `--video-id`指定時にチャンネルIDも必須にすると、ユーザーにとって冗長
  - ただし`SuggestService.suggest()`内で`channel_exists`チェックを行っており、channel_idが必要
  - video_ids指定時はチャンネルIDチェックをスキップし、指定された動画IDのみで動作させるのが自然
- **Implications**: `--video-id`指定時はchannel引数を不要にし、`SuggestOptions.channel_id`をオプショナルに変更。video_ids指定時はchannel_existsチェックをスキップ

## Design Decisions

### Decision: video_ids指定時のチャンネルID処理
- **Context**: `--video-id`指定時にチャンネル引数が必要かどうか
- **Alternatives Considered**:
  1. チャンネルID必須のまま — 既存動作を維持するが冗長
  2. `--video-id`指定時はチャンネルID省略可能 — ユーザー体験向上
- **Selected Approach**: `--video-id`指定時はチャンネル引数を不要にする
- **Rationale**: 動画IDが明示的に指定されている場合、チャンネル絞り込みは不要。ユーザーが知っているのは動画IDであり、そこからチャンネルを調べる手間を省く
- **Trade-offs**: チャンネル横断で動画IDを指定できるようになるが、これは利点として扱える

### Decision: バリデーション戦略
- **Context**: 存在しない動画IDの処理方法
- **Alternatives Considered**:
  1. CLI層でバリデーション — `search`パターン踏襲
  2. コアサービス層でバリデーション — ドメインロジックに集約
- **Selected Approach**: コアサービス層（`SuggestService`）でバリデーション
- **Rationale**: バリデーションと警告生成はドメインロジック。`search`ではコアサービス内でvalidate_video_idsを呼んでおり、同じ階層で処理するのが一貫性がある
- **Trade-offs**: サービスの戻り値に警告を含める必要がある

## Risks & Mitigations
- `DatabaseClient`にメソッド追加が必要 — 既存の`get_latest_videos`と同じパターンで実装すれば低リスク
- `SuggestOptions.channel_id`のオプショナル化 — 型安全に`channel_id: str | None`とし、video_ids未指定時は必須チェックをサービス内で行う
