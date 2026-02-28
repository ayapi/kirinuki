# Requirements Document

## Introduction

`youtube-live-clipper` で構築される字幕蓄積・話題セグメンテーション基盤の上に、「切り抜き候補の自動推薦」機能を追加する仕様。最新3件の配信アーカイブを対象に、切り抜きに適した話題区間をLLMが評価・推薦し、動画URL・区間・要約・魅力紹介をまとめて表示する。

### スコープ

**対象:**
- 最新アーカイブの自動選定（デフォルト3件）
- セグメントの切り抜き適性評価（LLMベース）
- 推薦結果の構造化表示（動画URL・区間・要約・魅力紹介）
- チャンネル単位での推薦実行

**対象外:**
- 動画のダウンロードや切り抜き動画の生成（将来フェーズ）
- 推薦ロジックのカスタマイズUI（将来フェーズ）

### 前提・依存

- `.kiro/specs/youtube-live-clipper` の Requirement 1（チャンネル登録と差分同期）、Requirement 2（ローカルデータ永続化）、Requirement 3（話題セグメンテーション）が実装済みであること
- 字幕データ・セグメントデータがSQLiteに蓄積されていること

---

## Requirements

### Requirement 1: 最新アーカイブの自動選定

**Objective:** ユーザーとして、チャンネルを指定するだけで最新の配信アーカイブが自動的に選ばれ、手動で動画を選ぶ手間なく推薦を受けたい。

#### Acceptance Criteria

1. When ユーザーがチャンネルを指定して推薦コマンドを実行した時, the kirinuki shall そのチャンネルの同期済みアーカイブから配信日時が新しい順に3件を自動選定する
2. When ユーザーが件数オプション（例: `--count 5`）を指定した時, the kirinuki shall デフォルトの3件ではなく指定された件数の最新アーカイブを選定する
3. If 指定チャンネルの同期済みアーカイブがデフォルト件数未満の場合, the kirinuki shall 利用可能な全アーカイブを対象とし、実際の対象件数を表示する
4. If 指定チャンネルに同期済みアーカイブが0件の場合, the kirinuki shall アーカイブが未同期である旨を表示し、同期コマンドの実行を案内する
5. The kirinuki shall 選定された各アーカイブのタイトルと配信日時を処理開始時に表示する

### Requirement 2: 切り抜き適性評価

**Objective:** ユーザーとして、話題セグメントの中から「切り抜きに向いている」ものをLLMが自動判定してほしい。人気が出そうな話題、面白い話題、独立して楽しめる話題を優先的に見つけたい。

#### Acceptance Criteria

1. When 対象アーカイブが選定された時, the kirinuki shall 各アーカイブの話題セグメントをLLMに送り、切り抜き適性を評価させる
2. The kirinuki shall 切り抜き適性の評価基準として、話題の独立性（文脈なしで楽しめるか）、エンタメ性（面白さ・意外性）、情報価値（有用な知識・ノウハウ）、感情的インパクト（共感・感動）を考慮する
3. The kirinuki shall 各セグメントに対して切り抜き推薦スコア（1〜10）を付与する
4. The kirinuki shall 推薦スコアが閾値（デフォルト: 7）以上のセグメントを切り抜き候補として抽出する
5. When ユーザーが閾値オプション（例: `--threshold 5`）を指定した時, the kirinuki shall デフォルトの閾値ではなく指定された閾値で候補を抽出する
6. If 全セグメントの推薦スコアが閾値未満の場合, the kirinuki shall 該当なしの旨を表示し、閾値を下げて再実行することを案内する

### Requirement 3: 推薦結果の構造化表示

**Objective:** ユーザーとして、推薦された切り抜き候補を一覧で見て、各候補の内容・魅力・該当区間を一目で把握したい。そのままブラウザで確認できるURLも欲しい。

#### Acceptance Criteria

1. The kirinuki shall 推薦結果を推薦スコアの降順で表示する
2. The kirinuki shall 各推薦候補に以下の情報を含める: 動画タイトル、配信日時、話題の要約（1〜2文）、切り抜きの魅力紹介（なぜこの部分が切り抜きに向いているかの説明）、推薦スコア、区間の開始時刻と終了時刻、タイムスタンプ付きYouTube URL
3. When 推薦結果を表示する時, the kirinuki shall 動画ごとにグループ化し、各動画内では時系列順にソートして表示する
4. The kirinuki shall タイムスタンプ付きYouTube URL（例: `https://www.youtube.com/watch?v=VIDEO_ID&t=START_SECONDS`）を生成し、クリックで該当区間から再生を開始できるようにする
5. When ユーザーが `--json` オプションを指定した時, the kirinuki shall 推薦結果を構造化されたJSON形式で出力する

### Requirement 4: CLIサブコマンド統合

**Objective:** ユーザーとして、既存のkirinuki CLIのサブコマンド体系に自然に統合された形で推薦機能にアクセスしたい。

#### Acceptance Criteria

1. The kirinuki shall 推薦機能をサブコマンド（例: `kirinuki suggest`）として提供する
2. When ユーザーが `kirinuki suggest <チャンネル指定>` を実行した時, the kirinuki shall 最新アーカイブの選定 → 切り抜き適性評価 → 結果表示の一連の処理を実行する
3. The kirinuki shall 処理の進捗（対象動画の選定中、セグメント評価中、結果表示）をステータスメッセージとして表示する
4. When コマンドが `--help` オプション付きで実行された時, the kirinuki shall 利用可能なオプション（`--count`, `--threshold`, `--json`）の説明を表示する
