# Research & Design Decisions

## Summary
- **Feature**: `default-channel-id`
- **Discovery Scope**: Extension（既存CLIコマンドへの機能追加）
- **Key Findings**:
  - 対象コマンドは `channel videos` と `suggest` の2つで、両方ともチャンネルIDを必須の位置引数として受け取る
  - `ChannelService.list_channels()` が既に全チャンネル一覧を返すAPIとして存在しており、チャンネル数の判定に利用可能
  - `suggest` コマンドは独自のDB接続（`DatabaseClient`）を使用しており、`ChannelService` を直接利用していない

## Research Log

### チャンネルID引数のClick定義パターン
- **Context**: 対象コマンドがチャンネルIDをどのように受け取っているか調査
- **Findings**:
  - `channel videos`: `@click.argument("channel_id")` — 必須位置引数
  - `suggest`: `@click.argument("channel")` — 必須位置引数
  - Clickの `@click.argument` はデフォルトで `required=True`。省略可能にするには `default=None, required=False` を設定する必要がある
- **Implications**: 両コマンドのClick引数定義を `required=False, default=None` に変更し、コールバック関数内でデフォルト解決ロジックを呼び出す設計が適切

### チャンネル一覧取得の既存API
- **Context**: デフォルトチャンネル解決に必要なチャンネル一覧取得方法の調査
- **Findings**:
  - `Database.list_channels()` → `list[ChannelSummary]` を返す（JOIN付きで `video_count` も取得）
  - `ChannelService.list_channels()` → 上記をラップ
  - `suggest` コマンドは `DatabaseClient`（`infra/db.py`）を使用しており、`Database`（`infra/database.py`）とは別のクライアント
- **Implications**: 解決ロジックをCLI層に配置するか、共通ユーティリティとして抽出するかの選択が必要。CLI層に配置する場合、`suggest` コマンドはDB接続が異なるため対応が必要

### suggestコマンドのアーキテクチャ差異
- **Context**: `suggest` コマンドが他コマンドと異なるDB接続パターンを使用している理由の調査
- **Findings**:
  - `main.py` のコマンド群: `create_app_context()` → `AppContext` → `ChannelService` を利用
  - `suggest`: 独自に `DatabaseClient` と `LLMClient` を直接生成。`AppContext` を経由しない
  - `suggest` は `cli.add_command(suggest_cmd, "suggest")` でメイングループに追加
- **Implications**: デフォルトチャンネル解決ロジックは両方のパターンで動作する必要がある。共通関数として `Database` にチャンネル一覧取得を提供するか、解決ロジック自体をCLI層の独立関数として実装する

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| CLI層ユーティリティ関数 | CLI層に `resolve_channel_id()` 関数を配置 | シンプル、既存アーキテクチャへの影響最小 | DB接続を引数で受ける必要あり | suggestの独自DB接続にも対応可能 |
| コアサービス層 | `ChannelService` にデフォルト解決メソッド追加 | ドメインロジックとしての配置が正当 | suggestコマンドがChannelServiceを利用していない | アーキテクチャ変更が大きい |
| Clickカスタムコールバック | Click の callback/type で自動解決 | 宣言的、各コマンド定義が簡潔 | Click依存、テストがやや複雑 | 過度な抽象化の懸念 |

## Design Decisions

### Decision: CLI層ユーティリティ関数パターンの採用
- **Context**: デフォルトチャンネル解決ロジックの配置先を決定
- **Alternatives Considered**:
  1. CLI層ユーティリティ関数 — `Database` インスタンスを受け取る単純な関数
  2. コアサービス層 — `ChannelService` にメソッド追加
  3. Clickカスタムコールバック — Click の型システムを活用
- **Selected Approach**: CLI層ユーティリティ関数
- **Rationale**: 既存の2つのDB接続パターン（`Database` / `DatabaseClient`）の両方をサポートする必要があり、CLI層に薄いユーティリティ関数を配置することで最小限の変更で済む。`Database.list_channels()` を利用してチャンネル一覧を取得し、件数に応じた分岐を行う
- **Trade-offs**: ドメインロジックがCLI層に漏れるが、ロジックは極めて単純（件数チェックのみ）であり、コアサービス層の変更を避けることで影響範囲を最小化できる
- **Follow-up**: `suggest` コマンドの `DatabaseClient` にも `list_channels` 相当のメソッドが必要か確認

## Risks & Mitigations
- `suggest` コマンドの `DatabaseClient` にチャンネル一覧取得メソッドがない可能性 → `Database.list_channels()` を共通で利用するか、必要に応じて追加
- 将来チャンネルIDを必要とする新コマンドが追加された場合の一貫性 → 解決関数を共通モジュールとして提供し、パターンを文書化
