# Implementation Plan

- [x] 1. `_base_opts()`にフォーマットエラー抑制オプションを追加する
  - 情報抽出用ベースオプションに`ignore_no_formats_error`を追加し、フォーマット選択エラーが発生しても字幕・メタデータの抽出を続行できるようにする
  - `download_video()`は独自のオプション辞書を使用しているため影響を受けないことを確認する
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 3.2_

- [x] 2. テストでオプション設定と既存動作の維持を検証する
- [x] 2.1 (P) `_base_opts()`のオプション検証テストを追加する
  - 返却辞書に`ignore_no_formats_error`と`skip_download`が含まれることを検証する
  - cookie存在時・非存在時の両方のケースを確認する
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2.2 (P) `download_video()`がフォーマットエラー抑制の影響を受けないことを検証するテストを追加する
  - `download_video()`のオプション辞書に`ignore_no_formats_error`が含まれないことを検証する
  - 既存のフォーマット指定が維持されていることを確認する
  - _Requirements: 3.1, 3.2_

- [x] 2.3 (P) フォーマット不可動画での情報抽出が成功することをモックテストで検証する
  - yt-dlpがフォーマット不可でもメタデータ・字幕を返すシナリオをモックで再現し、正常に処理されることを確認する
  - 真に利用不可な動画では`VideoUnavailableError`が引き続きraiseされることを検証する
  - _Requirements: 1.1, 1.2, 2.1, 2.2_
