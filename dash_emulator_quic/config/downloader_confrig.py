from dataclasses import dataclass
from enum import Enum


class DownloaderProtocolEnum(Enum):
    QUIC = 1
    TCP = 2


@dataclass
class DownloaderConfiguration:
    protocol: DownloaderProtocolEnum


def load_downloader_config(configuration) -> DownloaderConfiguration:
    return DownloaderConfiguration(protocol=DownloaderProtocolEnum[configuration["player"]["downloader"].upper()])
