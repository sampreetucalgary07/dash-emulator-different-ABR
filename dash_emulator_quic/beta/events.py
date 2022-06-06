from typing import Dict

from dash_emulator.models import State


class BETAEvent:
    pass


class BandwidthUpdateEvent(BETAEvent):
    def __init__(self, bw: int):
        self.bw = bw


class BytesTransferredEvent(BETAEvent):
    def __init__(self, length: int, url: str, position: int, size: int):
        self.size = size
        self.position = position
        self.url = url
        self.length = length


class BufferLevelChangeEvent(BETAEvent):
    def __init__(self, buffer_level):
        self.buffer_level = buffer_level


class StateChangeEvent(BETAEvent):
    def __init__(self, state: State):
        self.state = state


class SegmentDownloadStartEvent(BETAEvent):
    def __init__(self, index: int, selections: Dict[int, int]):
        self.index = index
        self.selections = selections


class SegmentDownloadCompleteEvent(BETAEvent):
    def __init__(self, index: int):
        self.index = index


class TransferStartEvent(BETAEvent):
    def __init__(self, url):
        self.url = url


class TransferEndEvent(BETAEvent):
    def __init__(self, size, url):
        self.size = size
        self.url = url


class TransferCancelEvent(BETAEvent):
    def __init__(self, url, position, size):
        self.url = url
        self.position = position
        self.size = size
