from argparse import Namespace
from typing import override

from snakeboot.command_line import CommandLineRunner


class TrainCommand(CommandLineRunner, command="train"):
    @override
    def run(self, arguments: Namespace) -> None: ...


class RetrainCommand(CommandLineRunner, command="train"):
    @override
    def run(self, arguments: Namespace) -> None: ...
