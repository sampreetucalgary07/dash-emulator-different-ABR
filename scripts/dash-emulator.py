#!/usr/bin/env python3

import argparse
import asyncio
import logging
import pathlib
import re
import sys
from typing import Dict, Union

import uvloop

from dash_emulator_quic.config import load_config_env
from dash_emulator_quic.player_factory import build_dash_player_over_quic

log = logging.getLogger(__name__)

PLAYER_TARGET = "target"

# print("All imports are done !! ")


def create_parser():
    arg_parser = argparse.ArgumentParser(description="Accept for the emulator")
    # Add here

    arg_parser.add_argument("--beta", action="store_true", help="Enable BETA")
    arg_parser.add_argument("--proxy", type=str, help="NOT IMPLEMENTED YET")
    arg_parser.add_argument(
        "--plot",
        required=False,
        default=None,
        type=str,
        help="The folder to save plots",
    )
    arg_parser.add_argument(
        "--dump-results",
        required=False,
        default=None,
        type=str,
        help="Dump the results",
    )
    arg_parser.add_argument(
        "--env", required=False, default=None, type=str, help="Environment to use"
    )
    arg_parser.add_argument(
        "--abr",
        required=False,
        default="bandwidth-based",
        type=str,
        help="Adaptation algorithm to use",
    )
    arg_parser.add_argument(
        "-y",
        required=False,
        default=False,
        action="store_true",
        help="Automatically overwrite output folder",
    )
    arg_parser.add_argument(
        "--num",
        required=False,
        default=1,
        type=int,
        help="Number of experiment repetition",
    )
    arg_parser.add_argument(PLAYER_TARGET, type=str, help="Target MPD file link")
    return arg_parser


def validate_args(arguments: Dict[str, Union[int, str, None]]) -> bool:
    # Validate target
    # args.PLAYER_TARGET is required
    if "target" not in arguments:
        log.error('Argument "%s" is required' % PLAYER_TARGET)
        return False
    # HTTP or HTTPS protocol
    results = re.match("^(http|https)://", arguments[PLAYER_TARGET])
    if results is None:
        log.error(
            'Argument "%s" (%s) is not in the right format'
            % (PLAYER_TARGET, arguments[PLAYER_TARGET])
        )
        return False

    # Validate proxy
    # TODO

    # Validate Output
    if arguments["plot"] is not None:
        path = pathlib.Path(arguments["plot"])
        path.mkdir(parents=True, exist_ok=True)

    return True


if __name__ == "__main__":
    try:
        assert sys.version_info.major >= 3 and sys.version_info.minor >= 3
    except AssertionError:
        print("Python 3.3+ is required.")
        exit(-1)
    # logging configuration
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)20s %(levelname)8s:%(message)s"
    )
    parser = create_parser()
    # parses the command-line arguments and stores them in the args variable as an object.
    args = parser.parse_args()

    # converts the parsed arguments into a dictionary for easier access.
    args = vars(args)

    validated = validate_args(args)

    if not validated:
        log.error("Arguments validation error, exit.")
        exit(-1)

    (player_config, downloader_config) = load_config_env(args["env"])

    uvloop.install()

    async def main():
        for i in range(args["num"]):  # no. of repetitions
            player, analyzer = build_dash_player_over_quic(
                player_config,
                downloader_config,
                beta=args["beta"],
                plot_output=args["plot"],
                dump_results=args["dump_results"],
                abr=args["abr"],
            )
            # player = build_dash_player()
            await player.start(args["target"])
            analyzer.save(sys.stdout)

    asyncio.run(main())
