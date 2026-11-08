import sys
from argparse import ArgumentParser, Namespace
from typing import override

from snakeboot.command_line import CommandLineRunner
from tests.application.sample_service.games.game_record import GameRecords


class CountGamesCommand(CommandLineRunner, command="count_games"):
    """Prints how many games have a status."""

    def __init__(self, games: GameRecords) -> None:
        self._games = games

    @classmethod
    @override
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--status", default="waiting")

    @override
    def run(self, arguments: Namespace) -> None:
        sys.stdout.write(f"{self._games.count_by_status(arguments.status)}\n")
