# Requirements Document

## Introduction
YouTube Liveアーカイブの切り抜き時、音ズレ補正やセグメンテーション精度の影響で話題の開始・終了が途切れることがある。TUI（`--tui`）フローで選択した区間を切り抜く際に、開始と終了にそれぞれ5秒のマージンを自動付与することで、話題の途切れを防止する。CLIの`clip`コマンドで直接時間指定した場合は、ユーザーが意図的に範囲を決めているため、マージンを適用しない。

## Requirements

### Requirement 1: TUI切り抜き時のマージン自動付与
**Objective:** TUIユーザーとして、選択した区間の切り抜き時に前後5秒のマージンが自動で付与されることで、音ズレ補正やセグメンテーション精度による話題の途切れを防ぎたい

#### Acceptance Criteria
1. When TUIフローで選択された区間の切り抜きを実行する, the ClipService shall 開始時刻を5秒前に、終了時刻を5秒後にそれぞれ拡張してダウンロード・切り抜きを行う
2. When マージン適用により開始時刻が負の値になる場合, the ClipService shall 開始時刻を0秒にクランプする
3. When マージン適用により終了時刻が動画の長さを超える場合, the ClipService shall yt-dlpの既定動作に委ね、動画末尾までを切り抜く（エラーにしない）

### Requirement 2: CLI clipコマンドでのマージン非適用
**Objective:** CLIユーザーとして、`clip`コマンドで直接時間範囲を指定した場合は指定した通りの範囲で切り抜かれることで、意図した正確な範囲の切り抜きを得たい

#### Acceptance Criteria
1. When ユーザーが`clip`コマンドで時間範囲を直接指定して切り抜きを実行する, the ClipService shall 指定された時間範囲をそのまま使用し、マージンを付与しない
2. The ClipService shall `clip`コマンド経由の切り抜きにおいて、従来の動作を一切変更しない

### Requirement 3: マージン値の設定
**Objective:** 開発者として、マージン秒数が定数として明示的に定義されていることで、将来の調整や設定化が容易な状態を保ちたい

#### Acceptance Criteria
1. The system shall マージン秒数をデフォルト値5秒の定数として定義する
2. The ClipService shall マージン適用の有無をリクエスト単位で制御できる仕組みを持つ
