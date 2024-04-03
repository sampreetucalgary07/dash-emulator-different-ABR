import asyncio
import os
import json
import logging
from abc import ABC, abstractmethod
from asyncio import Task
from typing import Dict, Optional, Set, List
import numpy as np

from scipy import stats

from dash_emulator.bandwidth import BandwidthMeter
from dash_emulator.buffer import BufferManager
from dash_emulator.models import AdaptationSet
from dash_emulator.scheduler import Scheduler, SchedulerEventListener

from dash_emulator_quic.abr import ExtendedABRController
from dash_emulator_quic.downloader.client import QuicClient


class BETAScheduler(Scheduler, ABC):
    @abstractmethod
    async def cancel_task(self, index):
        pass

    @abstractmethod
    async def drop_index(self, index):
        pass


class BETASchedulerImpl(BETAScheduler):
    log = logging.getLogger("BETASchedulerImpl")

    def __init__(
        self,
        max_buffer_duration: float,
        update_interval: float,
        download_manager: QuicClient,
        bandwidth_meter: BandwidthMeter,
        buffer_manager: BufferManager,
        abr_controller: ExtendedABRController,
        listeners: List[SchedulerEventListener],
    ):
        """
        Parameters
        ----------
        max_buffer_duration
            The maximum buffer duration.
            When available buffer longer than this value, the scheduler won't start new segment transmissions.
        update_interval
            The interval between updates if there's no download sessions
        download_manager
            A download manager to download video payloads
        bandwidth_meter
            An instance of bandwidth meter to estimate the bandwidth.
        buffer_manager
            An instance to provide the buffer information.
        abr_controller
            ABR Controller to update the representation selections.
        listeners
            A list of SchedulerEventHandler
        """

        self.max_buffer_duration = max_buffer_duration
        self.update_interval = update_interval

        self.download_manager = download_manager
        self.bandwidth_meter = bandwidth_meter
        self.buffer_manager = buffer_manager
        self.abr_controller = abr_controller
        self.listeners = listeners

        self.adaptation_sets: Optional[Dict[int, AdaptationSet]] = None
        self.started = False

        self._task: Optional[Task] = None
        self._index = 0
        self._representation_initialized: Set[str] = set()
        self._current_selections: Optional[Dict[int, int]] = None

        self._end = False
        self._dropped_index = None

        self.num_previous_samples = (
            3  # No. of previous samples to consider for slope calculation
        )
        self.slope_threshold = 0.33  # Threshold for slope calculation
        self.reduce_QL = (
            2  # Reduce quality level by this value if slope is less than threshold
        )

    def slope_estimator(self, q_list, slope_threshold=-0.33, reduce_QL=1):
        X = np.arange(len(q_list))
        slope, _, _, _, _ = stats.linregress(X, q_list)
        if slope > slope_threshold:
            return slope, reduce_QL, q_list
        else:
            return slope, 0, q_list

    async def loop(self):
        self.qual_list = []
        self.SBL_list = []
        self.SAL_list = []

        # self.log.info("BETA: Start scheduler loop from dash_emulator_quic")
        while True:
            # Check buffer level
            if self.buffer_manager.buffer_level > self.max_buffer_duration:
                await asyncio.sleep(self.update_interval)
                continue

            # Download one segment from each adaptation set
            self.log.info(
                f"index={self._index}, and dropped_index={self._dropped_index}"
            )
            if self._index == self._dropped_index:
                # print("self._index == self._dropped_index")
                selections = self.abr_controller.update_selection(
                    self.adaptation_sets, choose_lowest=True
                )
            else:
                selections = self.abr_controller.update_selection(self.adaptation_sets)

            self._current_selections = selections
            # print("index : ", self._index)
            # self.log.info(f"Selections  ={selections}")
            _sbl_value = self._current_selections[0]

            self.log.info(f"Selections before logic ={self._current_selections}")

            # print("Selections_before_logic : ", self._current_selections[0])
            # Select if you want to implement logic
            logic = False

            # Initialize slope, red_value and selected_values
            slope = "NA"
            red_value = 0
            selected_values = "NA"

            # calculate slope
            if logic == True and len(self.qual_list) > self.num_previous_samples:
                n = int(-1 * self.num_previous_samples)
                slope, red_value, selected_values = self.slope_estimator(
                    self.qual_list[n:], self.slope_threshold, self.reduce_QL
                )
                # self.log.info(f"slope={slope}")
                # print("slope : ", slope)

                self._current_selections[0] = self._current_selections[0] + red_value
                if self._current_selections[0] > 6:
                    self._current_selections[0] = 6

            # print("Selections_after_logic : ", self._current_selections[0])
            _sal_value = self._current_selections[0]
            # print("Selected_values : ", selected_values)

            self.qual_list.append(self._current_selections[0])

            # print("Len of Listener : ", len(self.listeners))
            for i, listener in enumerate(self.listeners):
                # print("Listener : ", listener)
                await listener.on_segment_download_start(self._index, selections)
                if i == 1:
                    await listener.store_logic_func_values(
                        _sbl_value, _sal_value, slope, red_value, selected_values
                    )
                    await listener.default_logic_func_values(
                        self.num_previous_samples,
                        self.slope_threshold,
                        self.reduce_QL,
                        logic,
                    )
            duration = 0
            urls = []
            for adaptation_set_id, selection in selections.items():
                adaptation_set = self.adaptation_sets[adaptation_set_id]
                representation = adaptation_set.representations.get(selection)
                representation_str = "%d:%d" % (adaptation_set_id, representation.id)
                if representation_str not in self._representation_initialized:
                    await self.download_manager.download(representation.initialization)
                    await self.download_manager.wait_complete(
                        representation.initialization
                    )
                    self.log.info(
                        f"Segment {self._index} Complete. Move to next segment"
                    )

                    self._representation_initialized.add(representation_str)
                try:
                    segment = representation.segments[self._index]
                except IndexError:
                    self._end = True
                    return

                urls.append(segment.url)
                await self.download_manager.download(segment.url)
                duration = segment.duration
            results = [await self.download_manager.wait_complete(url) for url in urls]
            if any([result is None for result in results]):
                # Result is None means the stream got dropped
                self._dropped_index = self._index
                continue
            for listener in self.listeners:
                await listener.on_segment_download_complete(self._index)
            self._index += 1
            self.buffer_manager.enqueue_buffer(duration)

    def start(self, adaptation_sets: Dict[int, AdaptationSet]):
        self.adaptation_sets = adaptation_sets
        self._task = asyncio.create_task(self.loop())

    def update(self, adaptation_sets: Dict[int, AdaptationSet]):
        self.adaptation_sets = adaptation_sets

    async def stop(self):
        await self.download_manager.close()
        if self._task is not None:
            self._task.cancel()

    @property
    def is_end(self):
        return self._end

    async def cancel_task(self, index: int):
        """
        Cancel current downloading task, and move to the next one

        Parameters
        ----------
        index: int
            The index of segment to cancel
        """

        # If the index is the the index of currently downloading segment, ignore it
        if self._index != index or self._current_selections is None:
            return

        # Do not cancel the task for the first index
        if index == 0:
            return

        for adaptation_set_id, selection in self._current_selections.items():
            segment = (
                self.adaptation_sets[adaptation_set_id]
                .representations[selection]
                .segments[self._index]
            )
            self.log.debug(f"BETA: Stop current downloading URL: {segment.url}")
            await self.download_manager.stop(segment.url)

    async def drop_index(self, index):
        self._dropped_index = index
