# Requirements Document

## Introduction
search、segments、suggestコマンドの結果をターミナル上でインタラクティブに操作するTUIモードを導入する。
ユーザーは結果一覧からSpaceキーで複数のセグメントを選択し、Enterキーで一括切り抜きを実行できる。
出力ファイル名は「動画ID-開始時間-話題名.mp4」の形式で自動生成される。

既存のsearch/segments/suggestコマンドのテキスト出力はそのまま維持し、新たに`--tui`フラグで切り替える方式とする。

## Requirements

### Requirement 1: TUIモードの起動
**Objective:** ユーザーとして、search・segments・suggestの各コマンドに`--tui`オプションを付けることで、結果をインタラクティブなTUI画面で表示したい。これにより、検索結果を確認しながらそのまま切り抜き操作に移行できる。

#### Acceptance Criteria
1. When ユーザーが`search`コマンドに`--tui`フラグを付けて実行した場合, the kirinuki CLI shall 検索結果をTUI画面に一覧表示する
2. When ユーザーが`segments`コマンドに`--tui`フラグを付けて実行した場合, the kirinuki CLI shall セグメント一覧をTUI画面に表示する
3. When ユーザーが`suggest`コマンドに`--tui`フラグを付けて実行した場合, the kirinuki CLI shall 推薦結果をTUI画面に一覧表示する
4. While `--tui`フラグが指定されていない場合, the kirinuki CLI shall 従来どおりのテキスト出力を行う（後方互換性）

### Requirement 2: TUI結果一覧の表示
**Objective:** ユーザーとして、TUI画面で各セグメントの情報（時間範囲、話題名、動画タイトルなど）を視認できるようにしたい。これにより、切り抜き対象を正確に判断できる。

#### Acceptance Criteria
1. The kirinuki TUI shall 各セグメントについて、時間範囲（MM:SS-MM:SS形式）と話題の要約を一覧に表示する
2. When searchコマンドの結果を表示する場合, the kirinuki TUI shall 動画タイトル、チャンネル名、スコア、マッチ種別を各行に含める
3. When suggestコマンドの結果を表示する場合, the kirinuki TUI shall 推薦スコア、動画タイトル、魅力ポイントを各行に含める
4. When segmentsコマンドの結果を表示する場合, the kirinuki TUI shall 動画IDに対応する全セグメントの時間範囲と要約を表示する
5. The kirinuki TUI shall カーソルキー（上下矢印）またはj/kキーで項目間を移動できるようにする

### Requirement 3: 複数選択機能
**Objective:** ユーザーとして、一覧から複数のセグメントをSpaceキーで選択・選択解除できるようにしたい。これにより、まとめて切り抜きを実行できる。

#### Acceptance Criteria
1. When ユーザーがSpaceキーを押した場合, the kirinuki TUI shall カーソル位置のセグメントの選択状態をトグルする（選択⇔未選択）
2. The kirinuki TUI shall 選択済みのセグメントにチェックマーク等の視覚的マーカーを表示する
3. The kirinuki TUI shall 現在の選択件数をステータス領域に表示する
4. While 1件以上のセグメントが選択されている場合, the kirinuki TUI shall Enterキーで切り抜き実行が可能であることをユーザーに示す

### Requirement 4: 切り抜き実行
**Objective:** ユーザーとして、選択したセグメントをEnterキーで一括切り抜きしたい。これにより、検索→選択→切り抜きの一連の操作をシームレスに行える。

#### Acceptance Criteria
1. When ユーザーがセグメントを選択した状態でEnterキーを押した場合, the kirinuki CLI shall 選択された全セグメントの切り抜き処理を実行する
2. While 切り抜き処理が実行中の場合, the kirinuki CLI shall 各セグメントの処理進捗（N件目/全M件）を表示する
3. When 切り抜き処理が完了した場合, the kirinuki CLI shall 成功件数・失敗件数と各出力ファイルパスを表示する
4. If セグメントが1件も選択されていない状態でEnterキーが押された場合, the kirinuki CLI shall 切り抜きを実行せずにその旨を通知する

### Requirement 5: 出力ファイル名の自動生成
**Objective:** ユーザーとして、切り抜きファイル名が「動画ID-開始時間-話題名.mp4」の形式で自動生成されてほしい。これにより、ファイル名から内容を容易に特定できる。

#### Acceptance Criteria
1. The kirinuki CLI shall 切り抜きファイル名を`{動画ID}-{開始時間}-{話題名}.mp4`の形式で生成する
2. The kirinuki CLI shall 開始時間をMM分SS秒形式（例: 18m03s）でファイル名に含める
3. The kirinuki CLI shall 話題名（セグメントのsummary）からファイル名に使用できない文字を除去またはサニタイズする
4. If 話題名が長すぎる場合, the kirinuki CLI shall 話題名を適切な長さに切り詰める
5. The kirinuki CLI shall 出力先ディレクトリとして既存のデフォルト出力先（`~/.kirinuki/output`）を使用する

### Requirement 6: TUI操作のキャンセルと終了
**Objective:** ユーザーとして、TUI画面からいつでも安全に離脱できるようにしたい。これにより、誤操作を防げる。

#### Acceptance Criteria
1. When ユーザーがqキーまたはEscキーを押した場合, the kirinuki TUI shall 切り抜きを実行せずにTUI画面を終了する
2. When ユーザーがCtrl+Cを押した場合, the kirinuki TUI shall 処理を中断しTUI画面を終了する
3. While 切り抜き処理実行中にCtrl+Cが押された場合, the kirinuki CLI shall 現在処理中のセグメントを完了後に残りをスキップし、それまでの結果を表示する
