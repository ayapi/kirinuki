# Requirements Document

## Introduction

`suggest`コマンドは現在、チャンネルの最新アーカイブN件を対象にLLMベースの切り抜き候補推薦を行うが、対象動画を個別に指定する手段がない。
本機能は`--video-id`オプションを追加し、特定の動画IDを指定して推薦対象を絞り込めるようにする。
これにより、ユーザーは「この動画の中からおすすめシーンを見たい」というユースケースに直接対応できる。
既存の`search`コマンドで`--video-id`が複数指定可能な実装パターンに倣い、一貫したCLIインターフェースを提供する。

## Requirements

### Requirement 1: --video-idオプションの追加
**Objective:** ユーザーとして、`suggest`コマンドで特定の動画IDを指定して推薦対象を絞り込みたい。それにより、関心のある動画だけのおすすめシーンを素早く確認できる。

#### Acceptance Criteria
1. When ユーザーが`suggest`コマンドに`--video-id`オプションを指定して実行した場合, the CLIは指定された動画IDのみを推薦対象とする
2. When ユーザーが`--video-id`を複数回指定した場合, the CLIは指定された全ての動画IDを推薦対象とする
3. When `--video-id`が省略された場合, the CLIは従来通り`--count`に基づく最新N件の動画を推薦対象とする（後方互換性を維持）
4. When `--video-id`と`--count`が同時に指定された場合, the CLIは`--video-id`を優先し、`--count`は無視する

### Requirement 2: 動画ID指定時のバリデーション
**Objective:** ユーザーとして、存在しない動画IDを指定した場合に分かりやすいエラーメッセージを得たい。それにより、入力ミスをすぐに修正できる。

#### Acceptance Criteria
1. If 指定された動画IDがDBに存在しない場合, the CLIはエラーメッセージを表示してユーザーに通知する
2. If 複数の動画IDを指定し一部がDBに存在しない場合, the CLIは存在する動画のみを対象に推薦を実行し、存在しない動画IDについて警告を表示する
3. If 指定された全ての動画IDがDBに存在しない場合, the CLIはエラーメッセージを表示して終了する

### Requirement 3: --video-id指定時の進捗表示
**Objective:** ユーザーとして、`--video-id`指定時にもどの動画が推薦対象になっているか確認したい。それにより、意図した動画が処理されていることを把握できる。

#### Acceptance Criteria
1. When `--video-id`で動画を指定して実行した場合, the CLIは対象動画のタイトルと公開日を進捗メッセージとして表示する
2. While JSON出力モード（`--json`）が有効な場合, the CLIは進捗メッセージをstderrに出力する（既存動作と一致）

### Requirement 4: TUIモードとの連携
**Objective:** ユーザーとして、`--video-id`と`--tui`を組み合わせて使いたい。それにより、特定動画のおすすめシーンをTUI上で選択・切り抜きできる。

#### Acceptance Criteria
1. When `--video-id`と`--tui`を同時に指定した場合, the CLIは指定動画の推薦結果をTUIモードで表示し、切り抜き実行が可能である
2. The `--video-id`オプションは既存の全オプション（`--count`, `--threshold`, `--json`, `--tui`）と組み合わせて使用できる

### Requirement 5: JSON出力対応
**Objective:** ユーザーとして、`--video-id`指定時のJSON出力でも動画IDフィルタリングが反映された結果を得たい。それにより、スクリプト連携でも動画ID絞り込みが利用できる。

#### Acceptance Criteria
1. When `--video-id`と`--json`を同時に指定した場合, the CLIは指定動画のみの推薦結果をJSON形式で出力する
2. The JSON出力の構造は既存のsuggest JSON出力と同一のスキーマを維持する
