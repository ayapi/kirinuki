"""ドメインエラー定義"""


class SegmentExtractorError(Exception):
    """archive-segment-extractorの基底例外"""


class InvalidURLError(SegmentExtractorError):
    """無効なYouTube URL"""


class TimeRangeError(SegmentExtractorError):
    """時間範囲が不正（超過、逆順等）"""


class AuthenticationRequiredError(SegmentExtractorError):
    """メンバー限定動画で認証情報が未設定"""


class VideoDownloadError(SegmentExtractorError):
    """動画ダウンロード失敗"""


class FfmpegNotFoundError(SegmentExtractorError):
    """ffmpegがインストールされていない"""


class ClipError(SegmentExtractorError):
    """ffmpegによる切り出し処理の失敗"""


class NoArchivesError(Exception):
    """同期済みアーカイブが0件の場合のエラー"""

    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id
        super().__init__(
            f"チャンネル '{channel_id}' に同期済みアーカイブがありません。"
            " `kirinuki sync` を実行して動画を同期してください。"
        )


class ChannelNotFoundError(Exception):
    """チャンネルが未登録の場合のエラー"""

    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id
        super().__init__(
            f"チャンネル '{channel_id}' は登録されていません。"
            " `kirinuki channel add` でチャンネルを登録してください。"
        )
