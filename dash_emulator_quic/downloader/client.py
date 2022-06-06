from abc import ABC, abstractmethod
from typing import Optional, Tuple

from dash_emulator.download import DownloadManager


class QuicClient(DownloadManager, ABC):
    @abstractmethod
    async def wait_complete(self, url: str) -> Optional[Tuple[bytes, int]]:
        """
        Wait the stream to complete

        Parameters
        ----------
        url:
            The URL to wait for

        Returns
        -------
            The return value could be None, meaning that the stream got dropped.
            It could be a tuple, the bytes as the first element and size as the second element.
        """
        pass

    @abstractmethod
    def cancel_read_url(self, url: str):
        pass

    @abstractmethod
    async def drop_url(self, url: str):
        """
        Drop the URL downloading process
        """
        pass