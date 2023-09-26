from typing import Tuple

from dash_emulator.abr import DashABRController
from dash_emulator.bandwidth import BandwidthMeterImpl
from dash_emulator.buffer import BufferManager, BufferManagerImpl
from dash_emulator.config import Config
from dash_emulator.event_logger import EventLogger
from dash_emulator.mpd import MPDProvider
from dash_emulator.mpd.parser import DefaultMPDParser
from dash_emulator.player import DASHPlayer
from dash_emulator.scheduler import Scheduler

from dash_emulator_quic.abr import ExtendedABRController, BetaABRController
from dash_emulator_quic.analyzers.analyer import (
    BETAPlaybackAnalyzer,
    BETAPlaybackAnalyzerConfig,
    PlaybackAnalyzer,
)
from dash_emulator_quic.beta.beta import BETAManagerImpl
from dash_emulator_quic.beta.vq_threshold import MockVQThresholdManager
from dash_emulator_quic.config import (
    PlayerConfiguration,
    DownloaderConfiguration,
    DownloaderProtocolEnum,
)
from dash_emulator_quic.downloader.tcp import TCPClientImpl
from dash_emulator_quic.mpd.providers import BETAMPDProviderImpl
from dash_emulator_quic.downloader.quic.client import QuicClientImpl
from dash_emulator_quic.downloader.quic.event_parser import H3EventParserImpl
from dash_emulator_quic.scheduler.scheduler import BETAScheduler, BETASchedulerImpl


def build_dash_player_over_quic(
    player_configuration: PlayerConfiguration,
    downloader_configuration: DownloaderConfiguration,
    beta=False,
    plot_output=None,
    dump_results=None,
    abr="",
) -> Tuple[DASHPlayer, PlaybackAnalyzer]:
    """
    Build a MPEG-DASH Player over QUIC network

    Returns
    -------
    player: Player
        A MPEG-DASH Player
    """
    BUFFER_DURATION = player_configuration.player_buffer_settings.buffer_duration  # 10
    SAFE_BUFFER_LEVEL = (
        player_configuration.player_buffer_settings.safe_buffer_level
    )  # 7.5
    PANIC_BUFFER_LEVEL = (
        player_configuration.player_buffer_settings.panic_buffer_level
    )  # 3
    MIN_REBUFFER_DURATION = (
        player_configuration.player_buffer_settings.min_rebuffer_duration
    )  # 2.5
    MIN_START_DURATION = (
        player_configuration.player_buffer_settings.min_start_duration
    )  # 2.5

    # we want to focus on non beta version
    if not beta:
        cfg = Config
        buffer_manager: BufferManager = BufferManagerImpl()
        event_logger = EventLogger()

        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(
                DefaultMPDParser(),
                cfg.update_interval,
                QuicClientImpl([], event_parser=H3EventParserImpl()),
            )
        else:  # this is the case
            mpd_provider: MPDProvider = BETAMPDProviderImpl(
                DefaultMPDParser(), cfg.update_interval, TCPClientImpl([])
            )

        analyzer: BETAPlaybackAnalyzer = BETAPlaybackAnalyzer(
            BETAPlaybackAnalyzerConfig(
                save_plots_dir=plot_output, dump_results_path=dump_results
            ),
            mpd_provider,
        )
        bandwidth_meter = BandwidthMeterImpl(
            cfg.max_initial_bitrate, cfg.smoothing_factor, [analyzer]
        )
        h3_event_parser = H3EventParserImpl(listeners=[bandwidth_meter, analyzer])
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            download_manager = QuicClientImpl(
                [bandwidth_meter, analyzer], event_parser=h3_event_parser
            )
        else:
            download_manager = TCPClientImpl([bandwidth_meter, analyzer])
        abr_controller = BetaABRController(
            DashABRController(
                PANIC_BUFFER_LEVEL,
                SAFE_BUFFER_LEVEL,
                bandwidth_meter,
                buffer_manager,
                abr,
                BUFFER_DURATION,
            )
        )
        scheduler: Scheduler = BETASchedulerImpl(
            BUFFER_DURATION,
            cfg.update_interval,  # 0.05
            download_manager,
            bandwidth_meter,
            buffer_manager,
            abr_controller,
            [event_logger, analyzer],
        )
        # print(type(abr_controller))
        # print(abr_controller)
        return (
            DASHPlayer(
                cfg.update_interval,
                min_rebuffer_duration=MIN_REBUFFER_DURATION,
                min_start_buffer_duration=MIN_START_DURATION,
                buffer_manager=buffer_manager,
                mpd_provider=mpd_provider,
                scheduler=scheduler,
                listeners=[event_logger, analyzer],
            ),
            analyzer,
        )
    else:  # this is NOT the case
        cfg = Config
        buffer_manager: BufferManager = BufferManagerImpl()
        event_logger = EventLogger()
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(
                DefaultMPDParser(),
                cfg.update_interval,
                QuicClientImpl([], H3EventParserImpl()),
            )
        else:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(
                DefaultMPDParser(), cfg.update_interval, TCPClientImpl([])
            )
        analyzer: BETAPlaybackAnalyzer = BETAPlaybackAnalyzer(
            BETAPlaybackAnalyzerConfig(
                save_plots_dir=plot_output, dump_results_path=dump_results
            ),
            mpd_provider,
        )
        bandwidth_meter = BandwidthMeterImpl(
            cfg.max_initial_bitrate, cfg.smoothing_factor, [analyzer]
        )
        h3_event_parser = H3EventParserImpl([bandwidth_meter, analyzer])
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            download_manager = QuicClientImpl(
                [bandwidth_meter, analyzer], h3_event_parser
            )
        else:
            download_manager = TCPClientImpl([bandwidth_meter, analyzer])

        vq_threshold_manager = MockVQThresholdManager()
        beta_manager = BETAManagerImpl(
            mpd_provider,
            download_manager,
            vq_threshold_manager,
            panic_buffer_level=PANIC_BUFFER_LEVEL,
            safe_buffer_level=SAFE_BUFFER_LEVEL,
        )
        download_manager.add_listener(beta_manager)
        bandwidth_meter.add_listener(beta_manager)
        h3_event_parser.add_listener(beta_manager)

        abr_controller: ExtendedABRController = BetaABRController(
            DashABRController(
                PANIC_BUFFER_LEVEL,
                SAFE_BUFFER_LEVEL,
                bandwidth_meter,
                buffer_manager,
                abr,
                BUFFER_DURATION,
            )
        )

        scheduler: BETAScheduler = BETASchedulerImpl(
            BUFFER_DURATION,
            cfg.update_interval,
            download_manager,
            bandwidth_meter,
            buffer_manager,
            abr_controller,
            [event_logger, beta_manager, analyzer],
        )

        return (
            DASHPlayer(
                cfg.update_interval,
                min_rebuffer_duration=MIN_REBUFFER_DURATION,
                min_start_buffer_duration=MIN_START_DURATION,
                buffer_manager=buffer_manager,
                mpd_provider=mpd_provider,
                scheduler=scheduler,
                listeners=[event_logger, beta_manager, analyzer],
                services=[beta_manager],
            ),
            analyzer,
        )
