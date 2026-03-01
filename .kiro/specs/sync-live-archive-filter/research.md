# Research & Design Decisions

## Summary
- **Feature**: `sync-live-archive-filter`
- **Discovery Scope**: Extension（既存syncパイプラインへのフィルタリング追加）
- **Key Findings**:
  - yt-dlpの `live_status` フィールドで `was_live` を判定可能
  - `extract_flat=True` モードでは `live_status` の取得が保証されない
  - 既存の `fetch_video_metadata()` 呼び出しから追加コストなしで `live_status` を取得可能

## Research Log

### yt-dlp live_status フィールドの仕様
- **Context**: ライブ配信アーカイブかどうかを判定する方法の調査
- **Sources Consulted**:
  - [yt-dlp man page (Arch)](https://man.archlinux.org/man/extra/yt-dlp/yt-dlp.1.en)
  - [yt-dlp Issue #8367](https://github.com/yt-dlp/yt-dlp/issues/8367)
  - [yt-dlp PyPI](https://pypi.org/project/yt-dlp/)
- **Findings**:
  - `live_status` は文字列フィールドで以下の値を取る:
    - `"not_live"` — 通常のアップロード動画
    - `"is_live"` — 現在配信中
    - `"is_upcoming"` — 配信予定（未開始）
    - `"was_live"` — 過去のライブ配信アーカイブ
    - `"post_live"` — 配信終了後、VOD未処理
  - `is_live` ブール値フィールドも存在するが、`live_status` の方が詳細な判定が可能
- **Implications**: `live_status == "was_live"` でライブ配信アーカイブを正確に識別可能

### extract_flat モードでのフィールド可用性
- **Context**: チャンネル全動画ID取得時（flat extraction）に `live_status` を取得できるか
- **Sources Consulted**:
  - yt-dlp公式ドキュメント: "some entry metadata may be missing"
  - [yt-dlp Issue #12828](https://github.com/yt-dlp/yt-dlp/issues/12828)
- **Findings**:
  - `extract_flat=True` ではエントリのメタデータが不完全になる可能性がある
  - `live_status` がflat extractionで確実に取得できる保証はない
  - YouTubeのブラウズAPIが返すフィールドはYouTube側の変更に依存
- **Implications**: flat extractionでの `live_status` 判定は信頼性が低い。個別のメタデータ取得で判定すべき

### 既存syncパイプラインの拡張ポイント
- **Context**: 最小限の変更でフィルタリングを組み込む方法
- **Findings**:
  - `_sync_single_video()` 内で `fetch_video_metadata()` → `fetch_subtitle()` の順に呼ばれている
  - `fetch_video_metadata()` は既に `yt_dlp.extract_info()` を呼んでおり、`info` dictに `live_status` が含まれる
  - メタデータ取得後・字幕取得前にフィルタリングすれば、不要な字幕取得を回避できる
  - 追加のAPI呼び出しは不要

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A: メタデータ取得後フィルタ | `fetch_video_metadata()` で `live_status` を返し、sync_serviceで判定 | 追加API呼び出し不要、信頼性高い | 非ライブ動画のメタデータ取得コストは残る | **採用** |
| B: `/streams` タブ使用 | チャンネルURLを `/streams` に変更 | flat extractionレベルで非ライブを排除 | yt-dlpの `/streams` タブ対応が不安定、アーカイブ漏れリスク | 不採用 |
| C: flat extraction時判定 | `list_channel_video_ids()` でentryの `live_status` を読む | 最も効率的（個別fetch不要） | `live_status` がflat modeで取得できる保証なし | 不採用 |

## Design Decisions

### Decision: メタデータ取得後のフィルタリング（Option A）
- **Context**: 非ライブ動画を排除するタイミングの決定
- **Alternatives Considered**:
  1. Option A — `fetch_video_metadata()` で `live_status` を取得し、sync service側で判定
  2. Option B — チャンネルURLを `/streams` タブに変更
  3. Option C — flat extraction時に `live_status` を読み取る
- **Selected Approach**: Option A
- **Rationale**:
  - 既存の `extract_info()` 呼び出しに `live_status` フィールドの読み取りを追加するだけで済む
  - 追加のAPI呼び出しが不要
  - yt-dlpのメタデータとして正式にサポートされたフィールド
  - flat extractionの不確実性に依存しない
- **Trade-offs**: 非ライブ動画1件あたり1回のメタデータ取得は発生するが、字幕取得（より重い処理）を回避できる
- **Follow-up**: 将来的に `/streams` タブの信頼性が確認できれば、Option Bとの併用でさらなる効率化が可能

## Risks & Mitigations
- **Risk**: yt-dlpの特定バージョンで `live_status` が `None` を返す可能性 → `None` の場合はスキップせずsync対象として処理（安全側に倒す）
- **Risk**: 既にsync済みの非ライブ動画がDBに存在する → 既存データには影響なし（差分syncのため新規動画のみ対象）
