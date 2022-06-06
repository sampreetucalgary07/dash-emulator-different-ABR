from abc import ABC, abstractmethod
from typing import Dict

from dash_emulator.abr import ABRController
from dash_emulator.models import AdaptationSet


class ExtendedABRController(ABC):
    @abstractmethod
    def update_selection(self, adaptation_sets: Dict[int, AdaptationSet], choose_lowest=False) -> Dict[int, int]:
        """
        Update the representation selections

        The main difference between this method and ABRController::update_selection is this method accepts an extra
        Parameter `choose_lowest`. When `choose_lowest` is True, return the lowest quality directly.

        Parameters
        ----------
        adaptation_sets:
            The adaptation sets information

        choose_lowest
            When this parameter is True, return the lowest quality for all adaptation sets directly.
        Returns
        -------
        selection:
            A dictionary where the key is the index of an adaptation set, and the
            value is the chosen representation id for that adaptation set.
        """
        pass


class BetaABRController(ExtendedABRController):
    def __init__(self, dash_abr_controller: ABRController):
        self.dash_abr_controller = dash_abr_controller

        self._min_bitrate_representations: Dict[int, int] = {}
        """
        Stores the representation id with the lowest bitrate (value) for the adaptation set id (key)
        """

    def _find_representation_id_of_lowest_bitrate(self, adaptation_set: AdaptationSet) -> int:
        """
        Find the representation ID with the lowest bitrate in a given adaptation set
        Parameters
        ----------
        adaptation_set:
            The adaptation set to process

        Returns
        -------
            The representation ID with the lowest bitrate
        """
        if adaptation_set.id in self._min_bitrate_representations:
            return self._min_bitrate_representations[adaptation_set.id]

        min_id = None
        min_bandwidth = None

        for representation in adaptation_set.representations.values():
            if min_bandwidth is None:
                min_bandwidth = representation.bandwidth
                min_id = representation.id
            elif representation.bandwidth < min_bandwidth:
                min_bandwidth = representation.bandwidth
                min_id = representation.id
        self._min_bitrate_representations[adaptation_set.id] = min_id

        return min_id

    def update_selection(self, adaptation_sets: Dict[int, AdaptationSet], choose_lowest=False) -> Dict[int, int]:
        if choose_lowest is True:
            results = {}
            for adaptation_set in adaptation_sets.values():
                results[adaptation_set.id] = self._find_representation_id_of_lowest_bitrate(adaptation_set)
            return results
        return self.dash_abr_controller.update_selection(adaptation_sets)
