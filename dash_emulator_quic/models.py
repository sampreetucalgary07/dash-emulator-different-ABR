from typing import Optional


class SegmentRequest:
    def __init__(self, index: int, url: Optional[str]):
        self.index = index
        self.url = url
        self.first_bytes_received = False
