import asyncio
from asyncio import Task
from typing import Optional

from dash_emulator.download import DownloadManager
from dash_emulator.models import MPD
from dash_emulator.mpd import MPDProvider
from dash_emulator.mpd.parser import MPDParser

from dash_emulator_quic.downloader.client import QuicClient


class BETAMPDProviderImpl(MPDProvider):
    def __init__(
        self, parser: MPDParser, update_interval: float, download_manager: QuicClient
    ):
        """
        Parameters
        ----------
        parser: MPDParser
            An MPDParser instance which parse the MPD text to MPD objects
        update_interval: float
            The interval between updating intervals if the mpd file is dynamic
        download_manager : DownloadManager
            The download manager instance
            This download manager should be a different instance from the one used to download video payloads
        """
        self.parser = parser
        self.update_interval = update_interval
        self.download_manager = download_manager

        self.mpd_url: Optional[str] = None
        self._mpd: Optional[MPD] = None
        self._task: Optional[Task] = None

    @property
    def mpd(self) -> MPD:
        return self._mpd

    async def update(self):
        await self.download_manager.download(self.mpd_url, save=True)
        content, size = await self.download_manager.wait_complete(self.mpd_url)
        # print("Dash Emulator Quic")
        # print("COntent : ", content)
        # print("Size : ", size)
        # print("URL : ", self.mpd_url)

        text = content.decode("utf-8")
        self._mpd = self.parser.parse(text, url=self.mpd_url)

    async def update_repeatedly(self):
        while True:
            await self.update()
            await asyncio.sleep(self.update_interval)

    async def start(self, mpd_url):
        self.mpd_url = mpd_url
        await self.update()
        if self._mpd.type == "dynamic":
            self._task = asyncio.create_task(self.update_repeatedly())
        else:
            asyncio.create_task(self.download_manager.close())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
        await self.download_manager.close()
