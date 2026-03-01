# Implementation Plan

- [x] 1. MatchType Enum と SearchResult モデルにマッチ理由フィールドを追加する
  - マッチ種別を表す StrEnum（keyword / semantic / hybrid の3値）を定義する
  - SearchResult に match_type（MatchType | None）、snippet（str | None）、similarity（float | None）の3フィールドを追加する
  - すべてデフォルト None として後方互換性を維持する
  - 既存の SkipReason と同じ StrEnum パターンを踏襲する
  - _Requirements: 1.1, 1.2, 1.3, 5.1, 5.2, 5.3_

- [x] 2. FTS検索とマージロジックの拡張
- [x] 2.1 (P) FTS検索クエリを拡張し、マッチした字幕テキストをスニペットとして返却する
  - fts_search_segments の SQL を変更し、GROUP_CONCAT でセグメント内のマッチ字幕行を連結して返す
  - DISTINCT を GROUP BY に変更し、集約関数を適用する
  - 区切り文字は「…」を使用する
  - 返却 dict に snippet キーを追加する
  - GROUP_CONCAT の結果が NULL の場合は空文字列で処理する
  - 既存のテストを更新し、snippet キーが含まれることを検証する
  - _Requirements: 2.1, 2.2_

- [x] 2.2 (P) SearchService のマージロジックにマッチ種別・スニペット・類似度の追跡を追加する
  - FTS 結果を処理する際に match_type=KEYWORD と snippet を中間データに記録する
  - ベクトル結果を処理する際に match_type=SEMANTIC と similarity（1.0 - distance）を中間データに記録する
  - 重複セグメント（FTS とベクトル両方でヒット）を検出した場合、match_type を HYBRID に更新し、snippet と similarity の両方を保持する
  - SearchResult 構築時に match_type、snippet、similarity を設定する
  - 既存のスコアリングロジックは変更しない
  - 既存のテストを更新し、マッチ種別が正しく設定されることを検証する
  - _Requirements: 1.1, 1.2, 1.3, 3.1, 5.4_

- [x] 3. CLI 検索結果の表示にマッチ理由行を追加する
  - 既存の表示行（動画情報、時間・要約、URL）は維持し、時間・要約行と URL 行の間にマッチ理由行を挿入する
  - キーワードマッチ時: マッチ種別ラベルとマッチした字幕スニペットを表示する
  - セマンティックマッチ時: マッチ種別ラベルと類似度をパーセンテージで表示する
  - 両方マッチ時: マッチ種別ラベルと字幕スニペット・類似度の両方を表示する
  - スニペットが80文字を超える場合は切り詰めて末尾に省略記号を付加する
  - 類似度は 0〜100% の整数パーセンテージに変換して表示する
  - match_type が None の場合はマッチ理由行を表示しない（後方互換）
  - 既存の CLI テストを更新し、マッチ理由行を含む出力を検証する
  - _Requirements: 2.3, 3.2, 4.1, 4.2, 4.3, 4.4_
