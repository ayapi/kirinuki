# Research & Design Decisions

## Summary
- **Feature**: `sync-live-archive-zero-count`
- **Discovery Scope**: Extension（既存システムの拡張）
- **Key Findings**:
  - YouTubeはライブ配信アーカイブを `/streams` タブに分離しており、`/videos` タブにはライブアーカイブが含まれないケースがある
  - yt-dlpの `extract_flat` は `/streams` パスでも同様に動作し、追加オプション不要
  - 現在の `list_channel_video_ids()` のインターフェースを変更せずに内部で複数タブをマージ可能

## Research Log

### YouTubeチャンネルのタブ構造
- **Context**: `list_channel_video_ids()` が `/videos` のみ参照しているが、ライブ配信アーカイブがそこに含まれない
- **Sources Consulted**: yt-dlpソースコード、YouTubeチャンネルページの構造
- **Findings**:
  - YouTubeチャンネルには `/videos`, `/streams`, `/shorts` 等のタブがある
  - ライブ配信のアーカイブ（`live_status=was_live`）は `/streams` タブに格納される
  - 通常の動画（`live_status=not_live` / `none`）は `/videos` タブに格納される
  - yt-dlpの `extract_flat=True` で `/streams` を指定すると、ライブアーカイブの動画IDリストが取得可能
- **Implications**: `/videos` と `/streams` の両方をフェッチし、結果をマージする必要がある

### 変更スコープの特定
- **Context**: 最小変更でどこを修正すべきか
- **Findings**:
  - `YtdlpClient.list_channel_video_ids()` — 内部で複数タブからフェッチしマージ（主な変更箇所）
  - `SyncService.sync_channel()` — インターフェース変更なし、修正不要
  - テスト — `list_channel_video_ids` のテスト更新（2回のextract_info呼び出しのモック）
- **Implications**: SyncServiceの呼び出し側は変更不要。YtdlpClient内で完結する変更

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A: YtdlpClient内部マージ | list_channel_video_idsが内部で両タブをフェッチ | SyncServiceの変更不要、インターフェース互換 | タブ単位の情報がログのみ | 推奨 |
| B: SyncService側マージ | 新メソッド追加でタブ別結果を返却 | SyncServiceでの可視性が高い | インターフェース変更、テスト変更が多い | 過剰 |

## Design Decisions

### Decision: YtdlpClient内部でのマルチタブフェッチ
- **Context**: `/videos` と `/streams` の両方から動画IDを取得する必要がある
- **Alternatives Considered**:
  1. Option A — `list_channel_video_ids()` 内部で `/videos` と `/streams` を順番にフェッチしマージ
  2. Option B — タブ別のメソッドを追加し、SyncServiceでマージ
- **Selected Approach**: Option A — 既存メソッド内部で両タブをフェッチ
- **Rationale**: SyncServiceのインターフェースを変更せず、後方互換性を完全に維持。可観測性はログ出力で十分
- **Trade-offs**: SyncServiceからタブ別カウントへの直接アクセスは不可（ログで代替）
- **Follow-up**: テスト時の `extract_info` モックが2回呼ばれることを検証

### Decision: フォールバック戦略
- **Context**: 片方のタブが失敗した場合の挙動
- **Selected Approach**: 各タブのフェッチを独立した try-except で囲み、片方の失敗を他方に影響させない
- **Rationale**: チャンネルによっては `/streams` タブが空またはエラーになる場合がある。部分的な結果でも同期を継続すべき

## Risks & Mitigations
- **yt-dlpの呼び出し回数が2倍になる** — チャンネルあたり2回のflat extraction。ネットワーク負荷は軽微（メタデータのみ）
- **YouTubeのタブ構造が変更される可能性** — タブの存在しないケースを既にフォールバックで対応済み

## References
- yt-dlp extract_flat documentation
- YouTube channel tab structure (videos / streams / shorts)
