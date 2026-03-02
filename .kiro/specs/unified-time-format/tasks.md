# Implementation Plan

- [x] 1. `format_time_range`ヘルパー関数を追加する
  - 開始秒数と終了秒数を受け取り、`MM:SS-MM:SS`形式（スペースなしハイフン区切り）の文字列を返すヘルパー関数を作成する
  - 既存の`format_time`関数を内部で利用し、2つの時刻文字列をハイフンで結合する
  - 1時間以上の場合は`H:MM:SS-H:MM:SS`形式になることを確認する（`format_time`の既存動作に依存）
  - _Requirements: 1.4, 3.1, 3.2_

- [x] 2. 各コマンドの時間範囲表示を統一フォーマットに置き換える
- [x] 2.1 (P) search・segmentsコマンドの時間範囲表示を修正する
  - searchコマンドの検索結果表示で、個別の`format_time`呼び出しと` - `区切りを`format_time_range`に置き換える
  - segmentsコマンドのセグメント一覧表示で、同様に`format_time_range`に置き換える
  - _Requirements: 1.1, 1.2_

- [x] 2.2 (P) suggestコマンドの時間範囲表示を修正する
  - 推薦結果のテキストフォーマッタで、`〜`（波ダッシュ）区切りの時間範囲表示を`format_time_range`に置き換える
  - _Requirements: 1.3_

- [x] 2.3 (P) clipコマンドの完了表示を修正する
  - clip成功時と失敗時の両方のサマリー表示で、` - `区切りの時間範囲を`format_time_range`に置き換える
  - _Requirements: 2.1_

- [x] 3. テストを追加しclipパーサーとのラウンドトリップを検証する
  - `format_time_range`の基本動作テスト：通常の秒数で正しい`M:SS-M:SS`形式を返すこと
  - `format_time_range`の1時間以上テスト：`H:MM:SS-H:MM:SS`形式を返すこと
  - ラウンドトリップテスト：`format_time_range`の出力をclipパーサー（`parse_time_ranges`）に渡して正しくパースされること
  - `format_time`の既存テストが引き続きパスすること（回帰確認）
  - _Requirements: 1.4, 1.5, 3.1_
