import asyncio
import logging
from typing import Optional, Tuple, List, Dict, Set

import aiohttp
from dash_emulator.download import DownloadEventListener

from dash_emulator_quic.downloader.client import QuicClient


class TCPClientImpl(QuicClient):
    log = logging.getLogger("TCPClientImpl")

    def __init__(self, event_listeners: List[DownloadEventListener]):
        self._event_listeners = event_listeners
        self._download_queue = asyncio.Queue()
        self._session = None
        self._session_close_event = asyncio.Event()
        self._is_busy = False
        self._downloading_task = None  # type: Optional[asyncio.Task]

        self._completed_urls = set()  # type: Set[str]
        self._partially_accepted_urls = set()  # type: Set[str]
        self._cancelled_urls = set()  # type: Set[str]

        self._headers = {}  # type: Dict[str, Dict[str, str]]
        self._content = {}  # type: Dict[str, bytearray]

        self._waiting_urls = {}  # type: Dict[str, asyncio.Event]

    async def wait_complete(self, url: str) -> Optional[Tuple[bytes, int]]:
        # If url is in partially accepted set, return read bytes and length
        if url in self._partially_accepted_urls:
            content = self._content[url]
            return bytes(content), int(self._headers[url]['CONTENT-LENGTH'])
        # If the url has been dropped, return None
        if url in self._cancelled_urls:
            return None
        # Wait the url to be completed
        if url not in self._completed_urls:
            self._waiting_urls[url] = asyncio.Event()
            await self._waiting_urls[url].wait()
            del self._waiting_urls[url]
        # If the url has been canceled, return None
        if url in self._cancelled_urls:
            self._cancelled_urls.remove(url)
            return None
        if url in self._completed_urls:
            self._completed_urls.remove(url)
        content = self._content[url]
        size = int(self._headers[url]['CONTENT-LENGTH'])
        return bytes(content), size

    def cancel_read_url(self, url: str):
        return

    async def drop_url(self, url: str):
        await self.stop(url)

    @property
    def is_busy(self):
        return self._is_busy

    async def download(self, url, save: bool = False) -> Optional[bytes]:
        self._waiting_urls[url] = asyncio.Event()
        self._content[url] = bytearray()
        if self._session is None:
            session_start_event = asyncio.Event()
            asyncio.create_task(self._create_session(session_start_event))
            await session_start_event.wait()

        for listener in self._event_listeners:
            await listener.on_transfer_start(url)
        await self._download_queue.put(url)
        return None

    async def _download_inner(self, url):
        async with self._session.get(url) as resp:
            self._headers[url] = resp.headers
            size = int(resp.headers['CONTENT-LENGTH'])
            async for chunk in resp.content.iter_chunked(10240):
                self._content[url] += bytearray(chunk)
                self.log.info(
                    f"Bytes transferred: length: {len(chunk)}, position: {len(self._content[url])}, size: {size}, url: {url}")
                for listener in self._event_listeners:
                    await listener.on_bytes_transferred(len(chunk), url, len(self._content[url]), size)
        self.log.info(f"Transfer ends: {len(self._content[url])}")
        self._completed_urls.add(url)
        self._waiting_urls[url].set()
        for listener in self._event_listeners:
            await listener.on_transfer_end(len(self._content[url]), url)

    async def _download_task(self):
        while True:
            self._is_busy = False
            req_url = await self._download_queue.get()
            self._is_busy = True

            self._downloading_task = asyncio.create_task(self._download_inner(req_url))

    async def _create_session(self, session_start_event):
        async with aiohttp.ClientSession() as session:
            self._session = session
            session_start_event.set()
            task = asyncio.create_task(self._download_task())
            await self._session_close_event.wait()
            task.cancel()

    async def close(self):
        if self._session_close_event is not None:
            self._session_close_event.set()

    async def stop(self, url: str):
        self.log.info("STOP DOWNLOADING: " + url)
        if self._downloading_task is not None:
            self._downloading_task.cancel()
        self._partially_accepted_urls.add(url)
        self._waiting_urls[url].set()
        for listener in self._event_listeners:
            await listener.on_transfer_end(len(self._content), url)

    def add_listener(self, listener: DownloadEventListener):
        self._event_listeners.append(listener)
