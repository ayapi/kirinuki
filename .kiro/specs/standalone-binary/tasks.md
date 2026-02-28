# Implementation Plan

- [x] 1. ビルド基盤のセットアップ
- [x] 1.1 (P) PyInstaller を dev 依存グループに追加する
  - `pyproject.toml` の `[dependency-groups] dev` に PyInstaller >= 6.0 を追加し、`uv sync` で反映する
  - _Requirements: 1.1, 2.1, 2.3_

- [x] 1.2 (P) sqlite-vec ネイティブ拡張をバンドルするための PyInstaller カスタムフックを作成する
  - `hooks/` ディレクトリに sqlite-vec 用のフックファイルを配置する
  - `vec0.dll` がバイナリ収集対象に含まれるようにする
  - _Requirements: 1.1_

- [x] 1.3 PyInstaller spec ファイルを作成する
  - エントリーポイントとして CLI のメインモジュールを指定する
  - onefile モードで `kirinuki.exe` を出力する設定にする
  - カスタムフックディレクトリを参照し、sqlite-vec パッケージ全体を収集対象に含める
  - pydantic, pydantic_settings 等の隠し依存を明示する
  - `src/` をインポートパスに含めてモジュール解決を行う
  - コンソールアプリケーションとして設定する（GUI ウィンドウなし）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1_

- [x] 2. ビルドを実行して kirinuki.exe の生成と動作を確認する
  - spec ファイルを使って PyInstaller を実行し、`dist/kirinuki.exe` が生成されることを確認する
  - `kirinuki.exe --help` でヘルプが正常に表示されることを確認する
  - 主要サブコマンド（channel list 等）がエラーなく実行できることを確認する
  - sqlite-vec を使う操作が正常に動作することを確認する（vec0.dll のバンドル検証）
  - 問題があれば spec やフックを修正して再ビルドする
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3. (P) README にバイナリの利用方法とビルド手順を追記する
  - 「インストール」セクションに、ビルド済みバイナリを PATH に配置するだけで使える旨と Windows 向け配置手順を追加する
  - 「必要なもの」セクションに、バイナリ利用時でも ffmpeg が別途必要である旨を明記する
  - 「開発」セクションに、PyInstaller でのビルドコマンドと前提条件を追加する
  - 「使い方」セクションの全コマンド例について、バイナリ利用時は `uv run` なしで `kirinuki` を直接実行できる旨を補記する
  - _Requirements: 2.2, 3.3, 4.1, 4.2, 4.3_
