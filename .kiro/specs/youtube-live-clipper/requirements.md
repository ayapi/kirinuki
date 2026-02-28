# Requirements Document

## Introduction

YouTube Liveの配信アーカイブから字幕・メタデータを取得してローカルに蓄積し、LLMによる話題セグメンテーションと横断検索を提供するCLIツールの要件。本フェーズでは「字幕データの蓄積」「話題分析」「検索による動画URL+区間の特定」までをスコープとし、動画のダウンロードや切り抜き動画の生成は対象外とする。

### スコープ

**対象:**
- 字幕・メタデータの取得と永続化
- LLMによる話題セグメンテーション
- キーワード・意味ベースの横断検索
- 検索結果としての動画URL+区間出力

**対象外（将来フェーズ）:**
- 動画ファイルのダウンロード
- ffmpegによる切り抜き動画生成
- 切り抜きのバッチ処理

---

## Requirements

### Requirement 1: チャンネル登録と差分同期

**Objective:** ユーザーとして、YouTubeチャンネルを登録し、そのチャンネルの全配信アーカイブの字幕を同期したい。翌日に新しい配信があれば、新しい分だけ差分取得したい。

#### Acceptance Criteria

1. When ユーザーがYouTubeチャンネルのURLまたはIDを指定して登録コマンドを実行した時, the kirinuki shall そのチャンネルを同期対象として登録する
2. When ユーザーが同期コマンドを実行した時, the kirinuki shall 登録済みチャンネルの配信アーカイブ一覧を取得し、未取得の動画の字幕・メタデータ（タイトル、配信日時、動画の長さ）のみを差分取得してローカルDBに保存する
3. The kirinuki shall 動画本体はダウンロードせず、字幕データとメタデータのみを取得する
4. While チャンネルにメンバー限定動画が含まれる場合, the kirinuki shall Cookie認証情報を使用してメンバー限定動画の字幕も取得対象に含める
5. When 字幕が自動生成字幕のみ利用可能な場合, the kirinuki shall 自動生成字幕をフォールバックとして取得する
6. If 動画に字幕が存在しない場合, the kirinuki shall その動画をスキップし、スキップした旨をログに記録する
7. The kirinuki shall 同期の進捗（取得済み/新規取得/スキップの件数）を表示する

### Requirement 2: ローカルデータ永続化

**Objective:** ユーザーとして、同期した字幕データが永続的に保存され、いつでも検索対象にできるようにしたい。

#### Acceptance Criteria

1. The kirinuki shall 字幕データ・メタデータ・セグメント情報をSQLiteデータベースに永続化する
2. The kirinuki shall 各動画をYouTubeの動画IDで一意に識別し、各チャンネルをチャンネルIDで一意に識別する
3. The kirinuki shall 字幕テキストをFTS（全文検索）インデックスに登録する
4. When ユーザーが登録チャンネル一覧コマンドを実行した時, the kirinuki shall 登録済みチャンネルと各チャンネルの同期済み動画数・最終同期日時を表示する
5. When ユーザーが特定チャンネルの動画一覧コマンドを実行した時, the kirinuki shall そのチャンネルの同期済み動画をタイトル・配信日時とともに表示する

### Requirement 3: 話題セグメンテーション

**Objective:** ユーザーとして、長時間配信の字幕を話題ごとに自動分割してほしい。それにより「何の話をどこでしていたか」が構造化された形で把握できるようにしたい。

#### Acceptance Criteria

1. When 動画の字幕取り込みが完了した時, the kirinuki shall LLMを使用して字幕テキストを話題単位のセグメントに分割する
2. The kirinuki shall 各セグメントに対して開始時刻、終了時刻、話題の要約テキストを生成し、DBに保存する
3. The kirinuki shall セグメントの要約テキストをベクトル化し、意味検索用インデックスに登録する
4. When ユーザーが特定動画のセグメント一覧表示コマンドを実行した時, the kirinuki shall その動画の話題セグメントを時系列順に要約テキストとともに表示する

### Requirement 4: 横断検索

**Objective:** ユーザーとして、「あのテーマについて話していた配信はどれ？どこで？」を自然言語で検索し、該当する動画と区間を見つけたい。

#### Acceptance Criteria

1. When ユーザーが検索クエリを入力した時, the kirinuki shall 保存済みの全動画のセグメントに対してキーワード検索と意味検索を実行し、関連度の高い順に結果を返す
2. The kirinuki shall 各検索結果に動画タイトル、チャンネル名、該当区間の開始・終了時刻、話題の要約テキストを含める
3. The kirinuki shall 検索結果に該当区間のタイムスタンプ付きYouTube URLを含め、ブラウザで直接その位置から再生できるようにする
4. When 検索結果が0件の場合, the kirinuki shall 該当なしの旨を表示する

### Requirement 5: Cookie認証管理

**Objective:** ユーザーとして、メンバー限定動画にアクセスするためのCookie認証を設定・管理したい。

#### Acceptance Criteria

1. The kirinuki shall ブラウザからエクスポートされたCookieファイルのパスを設定として保持する
2. When Cookie認証が設定されている時, the kirinuki shall メンバー限定動画の字幕取得にそのCookieを使用する
3. If Cookie認証が未設定の状態でメンバー限定動画が指定された場合, the kirinuki shall 認証が必要である旨のエラーメッセージを表示する

### Requirement 6: CLI基盤

**Objective:** ユーザーとして、直感的なサブコマンド体系で各機能にアクセスしたい。

#### Acceptance Criteria

1. The kirinuki shall サブコマンド形式のCLIインターフェースを提供する
2. The kirinuki shall 設定ファイルまたは環境変数によるLLM APIキー・Cookieパス等の設定をサポートする
3. When コマンドが`--help`オプション付きで実行された時, the kirinuki shall 利用可能なコマンドとオプションの説明を表示する
