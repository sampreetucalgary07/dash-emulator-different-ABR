from dataclasses import dataclass


@dataclass
class PlayerBufferSettings(object):
    buffer_duration: float
    safe_buffer_level: float
    panic_buffer_level: float
    min_rebuffer_duration: float
    min_start_duration: float


@dataclass
class PlayerConfiguration(object):
    player_buffer_settings: PlayerBufferSettings
    downloader: str


def load_player_config(configuration) -> PlayerConfiguration:
    player_buffer_settings = PlayerBufferSettings(**(configuration["player"]["buffer-settings"]))
    return PlayerConfiguration(player_buffer_settings, configuration['player']['downloader'])
