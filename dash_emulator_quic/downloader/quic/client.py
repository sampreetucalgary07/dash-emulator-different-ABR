import asyncio
import logging
from typing import List, Optional, Tuple, Set, AsyncIterator
from urllib.parse import urlparse

from aioquic.asyncio import connect
from aioquic.h3.connection import H3_ALPN
from aioquic.h3.events import H3Event
from aioquic.quic.configuration import QuicConfiguration
from aioquic.tls import SessionTicket
from dash_emulator.download import DownloadEventListener

from dash_emulator_quic.downloader.client import QuicClient
from dash_emulator_quic.downloader.quic.event_parser import H3EventParser
from dash_emulator_quic.downloader.quic.protocol import HttpProtocol


class QuicClientImpl(QuicClient):
    """
    QuickClientImpl will use only one thread, but be multiplexing by tuning a queue
    """

    log = logging.getLogger("QuicClientImpl")

    def __init__(self,
                 event_listeners: List[DownloadEventListener],
                 event_parser: H3EventParser,
                 session_ticket: Optional[SessionTicket] = None,
                 ):
        """
        Parameters
        ----------
        event_listeners: List[DownloadEventListener]
            A list of event listeners
        event_parser:
            Parse the H3Events
        session_ticket : SessionTicket, optional
            The ticket containing the authentication information.
            With this ticket, The QUIC Client can have 0-RTT on the first request (if the server allows).
            The QUIC Client will use 0-RTT for the following requests no matter if this parameter is provided.
        """
        self.quic_configuration = QuicConfiguration(alpn_protocols=H3_ALPN, is_client=True)
        self.event_parser = event_parser
        if session_ticket is not None:
            self.quic_configuration.session_ticket = session_ticket
        self.event_listeners = event_listeners

        self._client: Optional[HttpProtocol] = None

        self._close_event: Optional[asyncio.Event] = None
        """
        When this _close_event got set, the client will stop the connection completely.
        """

        self._canceled_urls: Set[str] = set()
        self._event_queue: Optional[asyncio.Queue[Tuple[H3Event, str]]] = None
        self._download_queue: Optional[asyncio.Queue[str]] = None

    @property
    def is_busy(self):
        """
        QUIC supports multiple streams in the same connection.
        It will be never busy because you can add a new request at any moment.

        Returns
        -------
        is_busy: bool
            False
        """
        return False

    async def wait_complete(self, url) -> Optional[Tuple[bytes, int]]:
        return await self.event_parser.wait_complete(url)

    async def close(self):
        # This is to close the whole connection
        if self._close_event is not None:
            self._close_event.set()

    async def stop(self, url: str):
        # This is to stop only one stream
        if self._client is not None:
            await self._client.close_stream_of_url(url)
            await self.event_parser.close_stream(url)

    def save_session_ticket(self, ticket: SessionTicket) -> None:
        """
        Callback which is invoked by the TLS engine when a new session ticket
        is received.
        """
        self.log.info("New session ticket received from server: " + ticket.server_name)
        self.quic_configuration.session_ticket = ticket

    async def _download_internal(self, url: str) -> AsyncIterator[Tuple[H3Event, str]]:
        self.log.info(f"Downloading Internal: {url}")
        async for event in self._client.get(url):
            yield event, url

    async def _download_loop(self):
        queue = asyncio.Queue()

        async def drain(iterator: AsyncIterator):
            async for i in iterator:
                await queue.put(i)

        async def read_new_request():
            while True:
                req_url = await self._download_queue.get()
                it = self._download_internal(req_url)
                asyncio.create_task(drain(it))

        asyncio.create_task(read_new_request())
        while True:
            event, url = await queue.get()
            await self.event_parser.parse(url, event)

    async def start(self, host, port, client_up_event=None):
        """
        Start the QUIC Client

        Parameters
        ----------
        host: str
            The hostname of the remote endpoint
        port: int
            The UDP port to connect to the remote endpoint
        client_up_event: asyncio.Event, optional
            If event is not None, set the event when the client is up
        """

        self._close_event = asyncio.Event()
        self._event_queue = asyncio.Queue()

        async with connect(
                host,
                port,
                configuration=self.quic_configuration,
                create_protocol=HttpProtocol,
                session_ticket_handler=self.save_session_ticket,
                local_port=0,
                wait_connected=False,
        ) as client:
            self._client = client
            # self._download_queue = asyncio.Queue()
            self._download_queue = asyncio.Queue()
            task = asyncio.create_task(self._download_loop())
            if client_up_event is not None:
                client_up_event.set()
            await self._close_event.wait()
            task.cancel()

        self._client = None
        self._close_event = None
        self._event_queue = None

    async def download(self, url: str, save=False) -> Optional[bytes]:
        # Client hasn't been started. Start the client.
        if self._client is None:
            parsed = urlparse(url)
            host = parsed.hostname
            if parsed.port is not None:
                port = parsed.port
            else:
                port = 443
            event = asyncio.Event()
            asyncio.create_task(self.start(host, port, client_up_event=event))
            await event.wait()

        for listener in self.event_listeners:
            await listener.on_transfer_start(url)
        await self._download_queue.put(url)
        return None

    def add_listener(self, listener: DownloadEventListener):
        if listener not in self.event_listeners:
            self.event_listeners.append(listener)

    def cancel_read_url(self, url: str):
        if self._client is not None:
            self._client.cancel_read(url)

    async def drop_url(self, url: str):
        if self._client is not None:
            await self._client.close_stream_of_url(url)
        await self.event_parser.drop_stream(url)
