from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, TypeVar, get_args, get_origin

T = TypeVar("T")


class Injection(Enum):
    """What an `@application_test` hands a field or a parameter that one of its markers annotates."""

    COMPONENT = "component"
    MOCK = "mock"
    SPY = "spy"


Autowired = Annotated[T, Injection.COMPONENT]
"""The component of type `T` of the started application, like `@Autowired`: `auctions: Autowired[AuctionRepository]`.

A type checker sees `T` itself. A test component is found by its own type too (`Autowired[FixedClock]`), and
`Autowired[RestClient]` is a client of the REST API.
"""

MockComponent = Annotated[T, Injection.MOCK]
"""A mock with the methods of `T` that replaces its component for one test, like `@MockitoBean`.

`when(self.invoices.save).then_raise(...)` says what it answers, `verify(self.invoices.save)` how it was called.
"""

SpyComponent = Annotated[T, Injection.SPY]
"""The component of type `T`, wrapped in a spy that records its calls, like `@MockitoSpyBean`.

It does what the component does, unless `when(...)` says otherwise; `verify(...)` checks how it was called. It replaces
the component before anything that depends on it is built, so it records what the event listeners call too.
"""


@dataclass(frozen=True, slots=True)
class InjectionPoint:
    """A field or a parameter of a test that its application fills: with what, and of which type."""

    injection: Injection
    component_type: Any


def injection_points(hints: Mapping[str, Any]) -> dict[str, InjectionPoint]:
    """The names among `hints`, from `typing.get_type_hints(..., include_extras=True)`, that a marker annotates."""
    points: dict[str, InjectionPoint] = {}
    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            component_type, *metadata = get_args(hint)
            injection = next((marker for marker in metadata if isinstance(marker, Injection)), None)
            if injection is not None:
                points[name] = InjectionPoint(injection, component_type)
    return points
