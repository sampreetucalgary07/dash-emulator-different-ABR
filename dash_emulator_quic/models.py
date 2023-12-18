from typing import Optional


class SegmentRequest:
    def __init__(self, index: int, url: Optional[str]):
        print("Dash Emulator Quic")
        print("SegmentRequest")
        print(index)
        print(url)
        self.index = index
        self.url = url
        self.first_bytes_received = False
