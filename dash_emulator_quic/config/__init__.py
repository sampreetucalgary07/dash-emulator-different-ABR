import logging
from typing import Tuple

import pkg_resources
import yaml

from .downloader_confrig import DownloaderConfiguration, load_downloader_config, DownloaderProtocolEnum
from .player_config import PlayerConfiguration, load_player_config

log = logging.getLogger(__name__)


def load_config_env(env_parameter: str) -> Tuple[PlayerConfiguration, DownloaderConfiguration]:
    if env_parameter is None or len(env_parameter) == 0:
        config_file_stream = pkg_resources.resource_stream('dash_emulator_quic', 'resources/application.yaml')
    else:
        try:
            config_file_stream = pkg_resources.resource_stream('dash_emulator_quic',
                                                               f'resources/application-{env_parameter}.yaml')
        except FileNotFoundError as e:
            log.warning(f"Cannot find application-{env_parameter}.yaml. Trying to load it as a full path")
            try:
                config_file_stream = open(env_parameter)
            except FileNotFoundError:
                config_file_stream = None

    if config_file_stream is None:
        raise FileNotFoundError(f"Cannot read configuration env: {env_parameter}")

    config_content = yaml.load(config_file_stream, Loader=yaml.Loader)

    player_configuration = load_player_config(config_content)
    downloader_confrig = load_downloader_config(config_content)
    return player_configuration, downloader_confrig
