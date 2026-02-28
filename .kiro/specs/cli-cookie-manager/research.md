# Research & Design Decisions

## Summary
- **Feature**: `cli-cookie-manager`
- **Discovery Scope**: Extension（既存CLIツールへの機能追加）
- **Key Findings**:
  - 現行のcookie管理は環境変数 `KIRINUKI_COOKIE_FILE_PATH` 経由でパスを指定する方式
  - `~/.kirinuki/` ディレクトリが既にデータ保存先（`data.db`）として使われている
  - yt-dlp統合層（`YtdlpClient`）は既に `cookiefile` オプションをサポート済み

## Research Log

### 既存のCookie管理フロー
- **Context**: 現状のcookies.txtの取り扱いを把握する
- **Sources Consulted**: `src/kirinuki/models/config.py`, `src/kirinuki/infra/ytdlp_client.py`, `.env.example`
- **Findings**:
  - `AppConfig.cookie_file_path` は `KIRINUKI_COOKIE_FILE_PATH` 環境変数から読み込み（`Path | None`）
  - `YtdlpClient._base_opts()` で `cookiefile` オプションとしてyt-dlpに渡される
  - `download_video()` はリクエスト単位の `cookie_file` オーバーライドもサポート
  - cookies未設定でメンバー限定動画にアクセスすると `AuthenticationRequiredError` が発生
- **Implications**: 固定パスに変更しても、YtdlpClientへの影響は `AppConfig` のデフォルト値変更のみで済む

### CLIコマンド構造の分析
- **Context**: 新しいcookieコマンドの追加方法を決定する
- **Sources Consulted**: `src/kirinuki/cli/main.py`, `src/kirinuki/cli/suggest.py`
- **Findings**:
  - Clickベースのコマンドグループ構成（`@click.group()`）
  - トップレベル: `cli` → サブグループ: `channel` → サブコマンド: `add`, `list`, `videos`
  - 独立コマンド: `sync`, `search`, `segments`, `suggest`
  - `create_app_context()` コンテキストマネージャでDI管理
- **Implications**: `cookie` コマンドグループを新設し、`set`/`status`/`delete` のサブコマンドを追加する構成が自然

### データディレクトリパターン
- **Context**: cookies.txtの固定保存先を決定する
- **Sources Consulted**: `src/kirinuki/models/config.py`
- **Findings**:
  - `db_path` のデフォルト値が `Path.home() / ".kirinuki" / "data.db"`
  - `~/.kirinuki/` がアプリケーションデータの標準保存先
- **Implications**: `~/.kirinuki/cookies.txt` が最も自然な固定パス

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 既存レイヤー拡張 | CLI層にcookieコマンド追加、core層にcookieサービス追加 | 既存パターンに準拠、変更量が少ない | なし | 採用 |
| インフラ層直接操作 | CLI層からファイル操作を直接実行 | シンプル | レイヤー分離原則に反する | 不採用 |

## Design Decisions

### Decision: Cookie保存パスの固定化
- **Context**: ユーザーが環境変数でcookies.txtのパスを指定する手間を排除する
- **Alternatives Considered**:
  1. `~/.kirinuki/cookies.txt`（アプリデータディレクトリ内）
  2. XDG Base Directory準拠（`~/.config/kirinuki/cookies.txt`）
- **Selected Approach**: `~/.kirinuki/cookies.txt`
- **Rationale**: 既に `db_path` が `~/.kirinuki/data.db` を使用しており、一貫性がある。XDGはLinux固有であり、クロスプラットフォーム対応が不要
- **Trade-offs**: XDG準拠ではないが、既存パターンとの一貫性を優先
- **Follow-up**: `AppConfig.cookie_file_path` のデフォルト値を固定パスに変更。環境変数は廃止

### Decision: Cookie入力方式
- **Context**: CLI上でcookiesの内容をペーストする方法
- **Alternatives Considered**:
  1. `click.edit()` によるエディタ起動
  2. 標準入力からの複数行読み取り（EOF終端）
  3. パイプ入力対応（`cat cookies.txt | kirinuki cookie set`）
- **Selected Approach**: 標準入力からの複数行読み取り + パイプ入力対応
- **Rationale**: `click.get_text_stream('stdin')` でインタラクティブ・パイプ両対応が可能。ペースト操作に最適
- **Trade-offs**: エディタ方式の方が編集しやすいが、「ペーストするだけ」という要件にはstdinが最適
- **Follow-up**: EOF入力の指示（Ctrl+D / Ctrl+Z）をプロンプトに表示

## Risks & Mitigations
- **環境変数との後方互換性** — 環境変数 `KIRINUKI_COOKIE_FILE_PATH` を廃止するため、既存ユーザーへの影響がある。固定パスへの移行ガイダンスを表示することで緩和
- **ファイルパーミッション** — cookies.txtには認証情報が含まれる。ファイル作成時にパーミッション600を設定

## References
- [yt-dlp Cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) — cookies.txtのNetscape形式について
- [Click Documentation](https://click.palletsprojects.com/en/stable/) — CLI入力パターン
