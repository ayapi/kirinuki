"""ドメインエラー定義"""


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
