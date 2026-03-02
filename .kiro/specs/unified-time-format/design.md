# Design Document: unified-time-format

## Overview
**Purpose**: search / suggest / segments コマンドの時間範囲表示をclipコマンドの引数形式（`MM:SS-MM:SS`）に統一し、コピペ運用を改善する。

**Users**: CLIユーザーが検索・推薦・セグメント表示の結果からclipコマンドに時間範囲を直接渡すワークフローで利用する。

**Impact**: 4箇所の時間範囲表示フォーマットを変更し、`format_time_range`ヘルパー関数を追加する。

### Goals
- 全コマンドの時間範囲表示を`MM:SS-MM:SS`（スペースなしハイフン区切り）に統一
- clipコマンドの`time_ranges`引数にそのまま渡せるフォーマットにする
- 既存の`format_time`関数は変更しない

### Non-Goals
- `format_time`関数の出力形式変更（ゼロパディング等）
- clipコマンドのパーサー側の変更
- JSON出力フォーマットの変更

## Architecture

### Existing Architecture Analysis
現在の時間範囲フォーマットは各CLI表示箇所で個別に実装されている：

| 箇所 | ファイル | 現在のフォーマット |
|------|---------|-------------------|
| search | `cli/main.py` L206 | `{start} - {end}` |
| segments | `cli/main.py` L230 | `{start} - {end}` |
| suggest | `core/formatter.py` L53 | `{start} 〜 {end}` |
| clip出力 | `cli/clip.py` L91, L100 | `({start} - {end})` |

全箇所で`format_time`を2回呼び出した後に文字列結合している。

### Architecture Pattern & Boundary Map

**Architecture Integration**:
- Selected pattern: 既存の`formatter.py`に`format_time_range`ヘルパーを追加する最小限の拡張
- Domain/feature boundaries: コアのフォーマッタ層で範囲表示を一元化し、CLI層は呼び出すのみ
- Existing patterns preserved: `format_time`関数のインターフェース・出力は不変
- New components rationale: `format_time_range`は範囲フォーマットの重複を排除するために追加
- Steering compliance: CLI層は薄く保つ原則に沿い、フォーマットロジックをコア層に集約

### Technology Stack

| Layer | Choice / Version | Role in Feature | Notes |
|-------|------------------|-----------------|-------|
| CLI | click | 表示出力（変更なし） | `format_time_range`を呼び出すのみ |
| Core | `formatter.py` | `format_time_range`関数追加 | 既存`format_time`を内部利用 |

## Requirements Traceability

| Requirement | Summary | Components | Interfaces |
|-------------|---------|------------|------------|
| 1.1 | searchの時間範囲フォーマット統一 | `cli/main.py` search | `format_time_range` |
| 1.2 | segmentsの時間範囲フォーマット統一 | `cli/main.py` segments | `format_time_range` |
| 1.3 | suggestの時間範囲フォーマット統一 | `core/formatter.py` RecommendationFormatter | `format_time_range` |
| 1.4 | 1時間以上動画のH:MM:SS形式対応 | `core/formatter.py` format_time_range | `format_time`（既存対応済み） |
| 1.5 | clipパーサーとの互換性 | 全コマンド出力 | clipパーサー検証（テスト） |
| 2.1 | clip出力の時間範囲フォーマット統一 | `cli/clip.py` | `format_time_range` |
| 3.1 | format_time出力不変 | `core/formatter.py` | 変更なし |
| 3.2 | 範囲区切り文字の一貫性 | `core/formatter.py` format_time_range | `-`（スペースなし） |

## Components and Interfaces

| Component | Domain/Layer | Intent | Req Coverage | Key Dependencies |
|-----------|-------------|--------|-------------|-----------------|
| `format_time_range` | Core / formatter | 2つの秒数から時間範囲文字列を生成 | 1.1-1.5, 2.1, 3.2 | `format_time` (P0) |
| search表示修正 | CLI / main | search出力のフォーマット変更 | 1.1 | `format_time_range` (P0) |
| segments表示修正 | CLI / main | segments出力のフォーマット変更 | 1.2 | `format_time_range` (P0) |
| suggest表示修正 | Core / formatter | suggest出力のフォーマット変更 | 1.3 | `format_time_range` (P0) |
| clip出力修正 | CLI / clip | clip完了表示のフォーマット変更 | 2.1 | `format_time_range` (P0) |

### Core Layer

#### `format_time_range`

| Field | Detail |
|-------|--------|
| Intent | 開始・終了秒数を`MM:SS-MM:SS`形式の文字列に変換する |
| Requirements | 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 3.2 |

**Responsibilities & Constraints**
- `format_time`を内部利用して開始・終了時刻を個別にフォーマットし、`-`で結合する
- `format_time`の出力仕様に依存する（`M:SS` / `H:MM:SS`）

**Dependencies**
- Inbound: `cli/main.py`, `cli/clip.py`, `RecommendationFormatter` — 時間範囲表示 (P0)
- Internal: `format_time` — 個別時刻フォーマット (P0)

**Contracts**: Service [x]

##### Service Interface
```python
def format_time_range(start_seconds: float, end_seconds: float) -> str:
    """2つの秒数を 'MM:SS-MM:SS' 形式の文字列に変換する。

    1時間以上の場合は 'H:MM:SS-H:MM:SS' 形式。
    clipコマンドのtime_ranges引数にそのまま渡せる形式を返す。
    """
    ...
```
- Preconditions: `start_seconds >= 0`, `end_seconds >= 0`
- Postconditions: 戻り値は`parse_time_ranges`で正しくパースできる
- Invariants: `format_time`の出力仕様が変わらない限り、clipパーサーとの互換性を維持

**Implementation Notes**
- 内部で`format_time(start_seconds)`と`format_time(end_seconds)`を呼び出し、`f"{start}-{end}"`で結合するのみ
- `format_time`自体の変更は不要（要件3.1）

### CLI Layer

#### search / segments / clip出力の修正

各箇所で個別の`format_time` 2回呼び出し+文字列結合を`format_time_range`の1回呼び出しに置き換える。

**変更箇所一覧**:

| ファイル | 行 | 変更内容 |
|---------|-----|---------|
| `src/kirinuki/cli/main.py` | L202-207 | search: `format_time` 2回 → `format_time_range` 1回 |
| `src/kirinuki/cli/main.py` | L226-230 | segments: `format_time` 2回 → `format_time_range` 1回 |
| `src/kirinuki/core/formatter.py` | L50-53 | suggest: `format_time` 2回+`〜`結合 → `format_time_range` 1回 |
| `src/kirinuki/cli/clip.py` | L88-91 | clip成功: `format_time` 2回 → `format_time_range` 1回 |
| `src/kirinuki/cli/clip.py` | L97-100 | clip失敗: `format_time` 2回 → `format_time_range` 1回 |

## Testing Strategy

### Unit Tests
- `format_time_range`の基本動作: 通常の秒数で`M:SS-M:SS`形式を返す
- `format_time_range`の1時間以上: `H:MM:SS-H:MM:SS`形式を返す
- `format_time_range`の出力をclipパーサー（`parse_time_ranges`）に渡してラウンドトリップ検証
- `format_time`の既存テストが引き続きパスすること

### Integration Tests
- search / segments / suggestコマンドの出力に`-`区切り（スペースなし）の時間範囲が含まれること
- clipコマンドの完了表示に`-`区切りの時間範囲が含まれること
