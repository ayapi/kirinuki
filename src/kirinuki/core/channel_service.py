"""チャンネル管理サービス"""

import logging

from kirinuki.infra.database import Database
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.domain import Channel, ChannelSummary, VideoSummary

logger = logging.getLogger(__name__)


class ChannelService:
    def __init__(self, db: Database, ytdlp_client: YtdlpClient) -> None:
        self._db = db
        self._ytdlp = ytdlp_client

    def register(self, channel_url: str) -> Channel:
        channel_id, channel_name = self._ytdlp.resolve_channel_name(channel_url)

        existing = self._db.get_channel(channel_id)
        if existing:
            logger.info("Channel %s is already registered", channel_id)
            return existing

        self._db.save_channel(channel_id, channel_name, channel_url)
        return Channel(channel_id=channel_id, name=channel_name, url=channel_url)

    def list_channels(self) -> list[ChannelSummary]:
        return self._db.list_channels()

    def list_videos(self, channel_id: str) -> list[VideoSummary]:
        return self._db.list_videos(channel_id)
