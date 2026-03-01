# Requirements Document

## Introduction
`kirinuki search <word>` コマンドの検索結果において、各結果がなぜヒットしたのかをユーザーが把握できるようにする。現状では、FTS検索は字幕テキストにマッチするがセグメントの要約（summary）のみ表示され、ベクトル検索は意味的類似度でマッチするが根拠が示されない。これにより、検索語と表示される話題の関連性が不明な結果が多く表示される問題がある。

## Requirements

### Requirement 1: マッチ種別の表示
**Objective:** ユーザーとして、検索結果ごとにキーワードマッチかセマンティックマッチかを区別できるようにしたい。これにより、結果の信頼性や関連性を判断しやすくなる。

#### Acceptance Criteria
1. When FTS検索のみでヒットした結果を表示する場合, the kirinuki CLI shall マッチ種別として「キーワード」を表示する
2. When ベクトル検索のみでヒットした結果を表示する場合, the kirinuki CLI shall マッチ種別として「セマンティック」を表示する
3. When FTS検索とベクトル検索の両方でヒットした結果を表示する場合, the kirinuki CLI shall マッチ種別として「キーワード+セマンティック」を表示する

### Requirement 2: キーワードマッチ時の字幕スニペット表示
**Objective:** ユーザーとして、キーワード検索でヒットした結果に対して、実際にマッチした字幕テキストの抜粋を確認したい。これにより、なぜその話題区間がヒットしたのかを具体的に理解できる。

#### Acceptance Criteria
1. When FTS検索でヒットした結果を表示する場合, the kirinuki CLI shall マッチした字幕テキストのスニペットを検索結果に含めて表示する
2. The kirinuki CLI shall 字幕スニペットは該当セグメント内でマッチした字幕行のテキストを含む
3. If マッチした字幕テキストが長すぎる場合, the kirinuki CLI shall スニペットを適切な長さに切り詰めて表示する

### Requirement 3: セマンティックマッチ時の類似度表示
**Objective:** ユーザーとして、セマンティック検索でヒットした結果の類似度を把握したい。これにより、検索語と話題の関連性の強さを判断できる。

#### Acceptance Criteria
1. When ベクトル検索でヒットした結果を表示する場合, the kirinuki CLI shall 類似度スコアを表示する
2. The kirinuki CLI shall 類似度スコアを0〜100%の範囲で表示する

### Requirement 4: 検索結果表示フォーマットの更新
**Objective:** ユーザーとして、マッチ理由を含む新しい検索結果フォーマットで直感的に結果を確認したい。これにより、検索結果の一覧性と理解しやすさが向上する。

#### Acceptance Criteria
1. The kirinuki CLI shall 各検索結果に対して、動画情報行（チャンネル名・動画タイトル）、時間範囲と話題要約の行、マッチ理由行、YouTube URLの行を表示する
2. When キーワードマッチの結果を表示する場合, the kirinuki CLI shall マッチ理由行に字幕スニペットを含めて表示する
3. When セマンティックマッチの結果を表示する場合, the kirinuki CLI shall マッチ理由行に類似度スコアを含めて表示する
4. When キーワードとセマンティックの両方でマッチした結果を表示する場合, the kirinuki CLI shall マッチ理由行に字幕スニペットと類似度スコアの両方を表示する

### Requirement 5: マッチ情報のデータ伝搬
**Objective:** 開発者として、検索結果にマッチ理由の情報を含められるようにしたい。これにより、CLI層で適切なフォーマットで表示できる。

#### Acceptance Criteria
1. The SearchResult model shall マッチ種別（FTS・ベクトル・両方）を保持するフィールドを持つ
2. The SearchResult model shall FTSマッチ時の字幕スニペットテキストを保持するフィールドを持つ
3. The SearchResult model shall ベクトル検索の類似度スコアを保持するフィールドを持つ
4. When SearchServiceがハイブリッド検索結果をマージする場合, the SearchService shall 各結果のマッチ種別・字幕スニペット・類似度スコアを正しく設定する
