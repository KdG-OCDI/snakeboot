"""The applications the tests of one run started, kept for the next test that asks the same one.

Like Spring's test context cache: starting an application is the slow part of a test of the whole application, and
most tests of a project ask the same one. What a test left behind is removed before the next one gets it.
"""

from collections import OrderedDict
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from unittest.mock import create_autospec

from snakeboot.testing.environment import TestEnvironment
from snakeboot.testing.slices import ApplicationSlice

if TYPE_CHECKING:
    from snakeboot.boot.testing import TestApplication

KEPT_AT_MOST: Final = 32
"""How many started applications a run keeps, like Spring's `spring.test.context.cache.maxSize`: beyond it, the one
that ran longest ago closes."""


@dataclass(frozen=True, slots=True)
class RunningApplication:
    """A started application with the mocks and the test components that were made for it."""

    application: "TestApplication"
    mocks: Mapping[Any, Any]
    test_components: tuple[object, ...]

    def reset(self) -> None:
        """Removes what a test left behind: see `TestApplication.reset`; every test component is built anew."""
        self.application.reset()
        for component in self.test_components:
            _build_anew(component)


@dataclass(frozen=True, slots=True)
class ApplicationSetUp:
    """What a test asks to be started: which application, where, how much of it, and what stands in for its parts.

    Two tests that ask the same get one started application, one after the other.
    """

    application: type
    environment: TestEnvironment
    only: ApplicationSlice | None
    mocked: tuple[Any, ...]
    spied: tuple[Any, ...]
    test_components: Mapping[Any, type]

    def key(self) -> Hashable:
        """What tells one set-up from another; a property's value counts by how it is written."""
        environment = self.environment
        properties = frozenset((name, repr(value)) for name, value in environment.properties.items())
        doubles = (frozenset(self.mocked), frozenset(self.spied), frozenset(self.test_components.items()))
        return (self.application, environment.profile, properties, environment.database, self.only, *doubles)

    def start(self) -> RunningApplication:
        """Starts the application, with a mock per mocked type, a spy per spied type and every test component built."""
        from snakeboot.boot.testing import SPY, TestApplication  # noqa: PLC0415  # reason: only a test that starts one needs it

        mocks = {mocked: create_autospec(mocked, instance=True) for mocked in self.mocked}
        # A spy is in place before the listeners are built, like @MockitoSpyBean before the beans that depend on it.
        spies = dict.fromkeys(self.spied, SPY)
        built = {replaced: _built(component) for replaced, component in self.test_components.items()}
        started = TestApplication.start(
            self.application,
            {**spies, **mocks},
            environment=self.environment,
            only=self.only,
            test_components=built,
        )
        return RunningApplication(started, mocks, tuple(built.values()))


class KeptApplications:
    """The started applications of a test run that no test is using now, by their set-up."""

    def __init__(self) -> None:
        self._kept: OrderedDict[Hashable, RunningApplication] = OrderedDict()

    def running(self, set_up: ApplicationSetUp) -> RunningApplication:
        """Hands the kept application of `set_up` to a test, or starts one; `keep` or close it afterwards."""
        kept = self._kept.pop(set_up.key(), None)
        if kept is None:
            return set_up.start()
        kept.application.resume()
        return kept

    def keep(self, set_up: ApplicationSetUp, running: RunningApplication) -> None:
        """Takes `running` back from its test, reset; an application that cannot be reset closes instead."""
        try:
            running.reset()
        except BaseException:
            running.application.close()
            raise
        self._kept[set_up.key()] = running
        while len(self._kept) > KEPT_AT_MOST:
            _, longest_ago = self._kept.popitem(last=False)
            longest_ago.application.close()

    def close(self) -> None:
        """Closes every kept application, when the test run ends."""
        while self._kept:
            _, kept = self._kept.popitem()
            kept.application.close()


def _built(component: type) -> object:
    try:
        return component()
    except TypeError as error:
        raise TypeError(f"A test component is built without arguments; {component.__qualname__}: {error}") from error


def _build_anew(component: Any) -> None:
    """Makes `component` what its class builds, in place: the application's components hold this very object."""
    fields = getattr(component, "__dict__", None)
    if fields is not None:
        fields.clear()
    component.__init__()
