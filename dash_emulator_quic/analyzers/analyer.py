import datetime
import io
import json
import os
from abc import ABC, abstractmethod
from typing import List, Tuple, TextIO, Optional, Dict

import matplotlib.pyplot as plt
from dash_emulator.bandwidth import BandwidthUpdateListener
from dash_emulator.download import DownloadEventListener
from dash_emulator.buffer import BufferManager
from dash_emulator.models import State
from dash_emulator.mpd import MPDProvider
from dash_emulator.player import PlayerEventListener
from dash_emulator.scheduler import SchedulerEventListener

# from dash_emulator_quic.scheduler import BETAScheduler, BETASchedulerImpl


class PlaybackAnalyzer(ABC):
    @abstractmethod
    def save(self, output: TextIO) -> None:
        """
        Save results to output
        """


class BETAPlaybackAnalyzerConfig:
    def __init__(self, save_plots_dir=None, dump_results_path=None):
        self.save_plots_dir = save_plots_dir
        self.dump_results_path = dump_results_path


class AnalyzerSegment:
    def __init__(
        self, index, start_time, completion_time, quality_selection, bandwidth
    ):
        self.index = index
        self.start_time = start_time
        self.completion_time = completion_time
        self.quality_selection = quality_selection
        self.bandwidth = bandwidth

        self.position = 0
        self.size = 0
        self.segment_bitrate = 0
        self.url = ""

    @property
    def ratio(self):
        return self.position / self.size


class BETAPlaybackAnalyzer(
    PlaybackAnalyzer,
    PlayerEventListener,
    SchedulerEventListener,
    DownloadEventListener,
    BandwidthUpdateListener,
):
    def __init__(self, config: BETAPlaybackAnalyzerConfig, mpd_provider: MPDProvider):
        self.config = config
        self._mpd_provider = mpd_provider
        self._start_time = datetime.datetime.now().timestamp()
        self._buffer_levels: List[Tuple[float, float]] = []
        self._throughputs: List[Tuple[float, int]] = []
        self._states: List[Tuple[float, State]] = []
        self._segments: List[AnalyzerSegment] = (
            []
        )  # start time, completion time, quality selection, bandwidth
        self._segments_by_url: Dict[str, AnalyzerSegment] = {}
        # self.values_list = BETASchedulerImpl.return_values()

        # index, start time, completion time, quality, bandwidth
        self._current_segment: Optional[AnalyzerSegment] = None

    @staticmethod
    def _seconds_since(start_time: float):
        """
        Calculate the seconds since a given time

        Parameters
        ----------
        start_time:
            The start time in seconds

        Returns
        -------
        The seconds sice given start_time

        """
        return datetime.datetime.now().timestamp() - start_time

    async def on_state_change(
        self, position: float, old_state: State, new_state: State
    ):
        self._states.append((self._seconds_since(self._start_time), new_state))

    async def on_buffer_level_change(self, buffer_level):
        self._buffer_levels.append(
            (self._seconds_since(self._start_time), buffer_level)
        )

    async def on_bytes_transferred(
        self, length: int, url: str, position: int, size: int
    ) -> None:
        segment = self._segments_by_url[url]
        segment.size = size
        segment.position = position

    async def on_transfer_end(self, size: int, url: str) -> None:
        pass

    async def on_transfer_start(self, url) -> None:
        self._current_segment.url = url
        self._segments_by_url[url] = self._current_segment

    async def on_transfer_canceled(self, url: str, position: int, size: int) -> None:
        pass

    async def on_segment_download_start(self, index, selections):
        throughput = self._throughputs[-1][1] if len(self._throughputs) != 0 else 0
        self._current_segment = AnalyzerSegment(
            index,
            self._seconds_since(self._start_time),
            None,
            selections[0],
            throughput,
        )

    async def on_segment_download_complete(self, index):
        completion_time = self._seconds_since(self._start_time)
        self._current_segment.completion_time = completion_time

        self._segments.append(self._current_segment)
        assert len(self._segments) == index + 1

    async def on_bandwidth_update(self, bw: int) -> None:
        self._throughputs.append((self._seconds_since(self._start_time), bw))

    def _get_video_representation(self, representation_id):
        """
        Get the video representation of given representation id

        Parameters
        ----------
        representation_id:
            The representation ID of the info

        Returns
        -------
        The video bitrate of given representation id

        """
        mpd = self._mpd_provider.mpd
        adaptation_set = None

        if len(mpd.adaptation_sets) != 1:
            return None

        for adaptation_set_id, adaptation_set_obj in mpd.adaptation_sets.items():
            if adaptation_set_obj.content_type == "video":
                adaptation_set = adaptation_set_obj
                break

        if adaptation_set is None:
            return None

        representation = adaptation_set.representations[representation_id]
        return representation

    def process_super_list(self, super_list, default_list):
        self.qual_list = super_list[0]
        self.SBL_list = super_list[1]
        self.SAL_list = super_list[2]
        self.slope_values = super_list[3]
        self.logic_values = super_list[4]
        self.selected_Values_list = super_list[5]
        self.num_previous_sample = default_list[0]
        self.slope_thre = default_list[1]

    def save(self, output: io.TextIOBase) -> None:
        bitrates = []

        last_quality = None
        quality_switches = 0

        total_stall_duration = 0
        total_stall_num = 0

        headers = (
            "Index",
            "Start",
            "End",
            "Quality",
            "Bitrate",
            "Throughut",
            "Ratio",
            "URL",
        )
        output.write("Length of the qual : " + str(len(self.qual_list)) + "\n")
        output.write("Length of the SBL list : " + str(len(self.SBL_list)) + "\n")
        output.write("Length of the SAL list : " + str(len(self.SAL_list)) + "\n")
        output.write("Length of the slope list : " + str(len(self.slope_values)) + "\n")
        output.write("Length of the logic list : " + str(len(self.logic_values)) + "\n")
        output.write(
            "Length of the num_previous_samples : "
            + str(self.num_previous_sample)
            + "\n"
        )
        output.write("Length of the slope_threshold : " + str(self.slope_thre) + "\n")
        output.write(
            "Length of the selected_values_list : "
            + str(len(self.selected_Values_list))
            + "\n"
        )
        output.write("\nQList from logic function:\n" + self.qual_list.__str__() + "\n")
        output.write("Selection before logic:\n" + self.SBL_list.__str__() + "\n")
        output.write("Selection after logic:\n" + self.SAL_list.__str__() + "\n")

        output.write("%-10s%-10s%-10s%-10s%-10s%-10s%-10s%-20s\n" % headers)

        for index, segment in enumerate(self._segments):
            if last_quality is None:
                # First segment
                last_quality = segment.quality_selection
            else:
                if last_quality != segment.quality_selection:
                    last_quality = segment.quality_selection
                    quality_switches += 1
            representation = self._get_video_representation(segment.quality_selection)
            bitrate = representation.bandwidth
            segment.segment_bitrate = bitrate
            bitrates.append(bitrate)
            output.write(
                "%-10d%-10.2f%-10.2f%-10d%-10d%-10d%-10.2f%-20s\n"
                % (
                    index,
                    segment.start_time,
                    segment.completion_time,
                    segment.quality_selection,
                    bitrate,
                    segment.bandwidth,
                    segment.ratio,
                    segment.url,
                )
            )
            # output.write(self._buffer_levels.__str__())
        output.write("\n")

        # Stalls
        output.write("Stalls:\n")
        output.write("%-10s%-10s%-10s\n" % ("Start", "End", "Duration"))
        buffering_start = None
        stall_info_list = []
        for time, state in self._states:
            if state == State.BUFFERING:
                buffering_start = time
            elif state == State.READY:
                if buffering_start is not None:
                    duration = time - buffering_start
                    output.write(
                        "%-10.2f%-10.2f%-10.2f\n" % (buffering_start, time, duration)
                    )
                    stall_info_list.append((buffering_start, time, duration))
                    total_stall_num += 1
                    total_stall_duration += duration
                    buffering_start = None

        output.write("\n")
        output.write("Stall info list:\n")
        output.write(stall_info_list.__str__() + "\n")

        # Stall summary
        output.write(f"Number of Stalls: {total_stall_num}\n")
        output.write(f"Total seconds of stalls: {total_stall_duration}\n")

        # Average bitrate
        average_bitrate = sum(bitrates) / len(bitrates)
        output.write(f"Average bitrate: {average_bitrate:.2f} bps\n")

        # Number of quality switches
        output.write(f"Number of quality switches: {quality_switches}\n")

        output.write("\n")

        if self.config.save_plots_dir is not None:
            self.save_plot()

        if self.config.dump_results_path is not None:
            self.dump_results(
                self.config.dump_results_path,
                self._segments,
                total_stall_num,
                total_stall_duration,
                stall_info_list,
                average_bitrate,
                quality_switches,
                self.SBL_list,
                self.SAL_list,
                self.slope_values,
                self.logic_values,
                self.selected_Values_list,
                self.num_previous_sample,
                self.slope_thre,
            )

    @staticmethod
    def dump_results(
        path,
        segments: List[AnalyzerSegment],
        num_stall,
        dur_stall,
        stall_info_list,
        avg_bitrate,
        num_quality_switches,
        SAL,
        SBL,
        slope_values,
        logic_values,
        selected_Values_list,
        num_previous_sample,
        slope_thre,
    ):
        print("Dumping results to " + path + "\n")
        data = {"segments": []}
        for segment, svb, sal, slope_value, logic, selected_values in zip(
            segments,
            SAL,
            SBL,
            slope_values,
            logic_values,
            selected_Values_list,
        ):
            data_obj = {
                "index": segment.index,
                "start": segment.start_time,  # when the player starts downloading the segment
                "end": segment.completion_time,  # when the player finishes downloading the segment
                "quality": segment.quality_selection,  # quality requested by the player
                "bitrate": segment.segment_bitrate,  # bitrate of the segment
                "throughput": segment.bandwidth,
                "ratio": segment.ratio,
                "url": segment.url,
                "selection_before_logic": svb,
                "selection_after_logic": sal,
                "slope_value": slope_value,
                "logic_enabled": logic,
                "values_for_slope": selected_values,
            }
            data["segments"].append(data_obj)

        data["num_stall"] = num_stall
        data["dur_stall"] = dur_stall
        data["stall_info_list"] = stall_info_list
        data["avg_bitrate"] = avg_bitrate
        data["num_quality_switches"] = num_quality_switches
        data["num_previous_sample"] = num_previous_sample
        data["Slope_threshold"] = slope_thre

        extra_index = 1
        final_path = f"{path}-{extra_index}.json"
        while os.path.exists(final_path):
            extra_index += 1
            final_path = f"{path}-{extra_index}.json"

        with open(final_path, "w") as f:
            f.write(json.dumps(data))

    def save_plot(self):
        def plot_bws(ax: plt.Axes):
            xs = [i[0] for i in self._throughputs]
            ys = [i[1] / 1000 for i in self._throughputs]
            lines1 = ax.plot(xs, ys, color="red", label="Throughput")
            ax.set_xlim(0)
            ax.set_ylim(0)
            ax.set_xlabel("Time (second)")
            ax.set_ylabel("Bandwidth (kbps)", color="red")
            return (*lines1,)

        def plot_bufs(ax: plt.Axes):
            xs = [i[0] for i in self._buffer_levels]
            ys = [i[1] for i in self._buffer_levels]
            line1 = ax.plot(xs, ys, color="blue", label="Buffer")
            ax.set_xlim(0)
            ax.set_ylim(0)
            ax.set_ylabel("Buffer (second)", color="blue")
            line2 = ax.hlines(1.5, 0, 20, linestyles="dashed", label="Panic buffer")
            return *line1, line2

        output_file = os.path.join(self.config.save_plots_dir, "status.pdf")
        fig: plt.Figure
        ax1: plt.Axes
        fig, ax1 = plt.subplots()
        ax2: plt.Axes = ax1.twinx()
        lines = plot_bws(ax1) + plot_bufs(ax2)
        labels = [line.get_label() for line in lines]
        fig.legend(lines, labels)
        fig.savefig(output_file)
