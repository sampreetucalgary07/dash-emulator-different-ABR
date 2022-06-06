from abc import ABC, abstractmethod


class VQThresholdManager(ABC):
    @abstractmethod
    def get_threshold(self, index) -> float:
        """
        Return the VQ threshold (0.0 ~ 1.0) of the given index
        """
        pass


class MockVQThresholdManager(VQThresholdManager):
    def get_threshold(self, index) -> float:
        return 0.8
