"""Lifecycle components that write down what happens to them."""

from abc import abstractmethod
from typing import ClassVar, override

from snakeboot.lifecycle import Lifecycle


class Journal:
    """Stands in for whatever a component touches: the order of starts and stops."""

    def __init__(self) -> None:
        self.entries: list[str] = []


class Recording(Lifecycle, component=False):
    """Writes down its start and its stop; `failing` makes one of them raise."""

    def __init__(self, journal: Journal, name: str, failing: str = "") -> None:
        self._journal = journal
        self._name = name
        self._failing = failing

    @override
    def start(self) -> None:
        self._note("start")

    @override
    def stop(self) -> None:
        self._note("stop")

    def _note(self, what: str) -> None:
        if what == self._failing:
            raise RuntimeError(f"{self._name} cannot {what}")
        self._journal.entries.append(f"{what} {self._name}")


class Early(Recording, component=False):
    """Starts before the default phase."""

    phase: ClassVar[int] = -1


class Wired(Lifecycle):
    """Stands in for a component of an application, found by wireup."""

    def __init__(self, journal: Journal) -> None:
        self._journal = journal

    @override
    def start(self) -> None:
        self._journal.entries.append("start wired")

    @override
    def stop(self) -> None:
        self._journal.entries.append("stop wired")


class StillAbstract(Lifecycle):
    """A base that leaves `stop` to its subclasses, so it is no component."""

    @override
    def start(self) -> None: ...

    @abstractmethod
    @override
    def stop(self) -> None: ...
