import bisect
import logging
import math
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Final, Literal

logger = logging.getLogger(__name__)

DEFAULT_BUCKETS: Final = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
"""The upper bounds, in seconds, of the histogram of a timer: from 5 milliseconds to 10 seconds."""

CONTENT_TYPE: Final = "text/plain; version=0.0.4; charset=utf-8"
"""The type of `scrape()`'s text: Prometheus's text exposition format."""

_NAME: Final = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
_TAG: Final = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

type Tags = Mapping[str, str]
type _Kind = Literal["counter", "histogram", "gauge"]
type _TagValues = tuple[tuple[str, str], ...]


class InvalidMeterError(ValueError):
    """Raised when a meter cannot be registered: a name Prometheus refuses, or one name for two kinds of meter."""


class Counter:
    """A number that only goes up, like Micrometer's `Counter`: games started, messages refused."""

    def __init__(self) -> None:
        self._value = 0.0
        self._lock = threading.Lock()

    @property
    def value(self) -> float:
        """How much it counted so far."""
        return self._value

    def increment(self, amount: float = 1.0) -> None:
        """Counts `amount` more; a counter never goes down."""
        if amount < 0:
            raise InvalidMeterError(f"A counter only goes up, not by {amount}.")
        with self._lock:
            self._value += amount


class Timer:
    """How long something takes, as a histogram, like Micrometer's `Timer` with its percentiles histogram.

    with self._meters.timer("game_ai_move_seconds", "How long the AI thinks").time():
        move = self._ai.next_move(board)
    """

    def __init__(self, buckets: tuple[float, ...] = DEFAULT_BUCKETS) -> None:
        self._buckets = buckets
        self._counts = [0] * (len(buckets) + 1)
        self._sum = 0.0
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        """How many durations it recorded."""
        return sum(self._counts)

    @property
    def total_seconds(self) -> float:
        """The sum of the durations it recorded."""
        return self._sum

    def record(self, seconds: float) -> None:
        """Records one duration."""
        with self._lock:
            self._counts[bisect.bisect_left(self._buckets, seconds)] += 1
            self._sum += seconds

    @contextmanager
    def time(self) -> Iterator[None]:
        """Records how long the block takes, whether it returns or raises."""
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record(time.perf_counter() - started)

    def cumulative(self) -> list[tuple[float, int]]:
        """Each upper bound, `inf` last, with how many durations were at most that long."""
        with self._lock:
            counts = list(self._counts)
        bounds = [*self._buckets, math.inf]
        return [(bound, sum(counts[: index + 1])) for index, bound in enumerate(bounds)]


@dataclass
class _Family:
    name: str
    description: str
    kind: _Kind
    meters: dict[_TagValues, object] = field(default_factory=dict)


class MeterRegistry:
    """The application's metrics, which `/metrics` hands Prometheus, like Micrometer's `PrometheusMeterRegistry`.

    An adapter asks for it by type and registers its meters by name and tags; the same name and tags give the same
    meter, so a hot path may ask each time. The web binding times every call (`http_server_requests_seconds`, tagged
    with the method, the route and the status).

        self._meters.counter("games_started", "Games started", tags={"game": "tictactoe"}).increment()

    It counts in this process: with several `[server] workers`, Prometheus sees whichever answers, so scale with
    replicas of one worker instead.
    """

    def __init__(self) -> None:
        self._families: dict[str, _Family] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, description: str, *, tags: Tags | None = None) -> Counter:
        """Returns the counter of `name` and `tags`, registered at the first call; Prometheus sees `<name>_total`."""
        counter = self._meter(_Family(name.removesuffix("_total"), description, "counter"), tags, Counter)
        if not isinstance(counter, Counter):
            raise InvalidMeterError(f"{name} is no counter.")
        return counter

    def timer(self, name: str, description: str, *, tags: Tags | None = None) -> Timer:
        """Returns the timer of `name` and `tags`, registered at the first call; name it `..._seconds`."""
        timer = self._meter(_Family(name, description, "histogram"), tags, Timer)
        if not isinstance(timer, Timer):
            raise InvalidMeterError(f"{name} is no timer.")
        return timer

    def gauge(self, name: str, description: str, read: Callable[[], float], *, tags: Tags | None = None) -> None:
        """Registers a value that `read` gives whenever Prometheus asks: a queue's length, a pool's free connections."""
        self._meter(_Family(name, description, "gauge"), tags, lambda: read)

    def scrape(self) -> str:
        """Returns every meter in Prometheus's text exposition format."""
        with self._lock:
            families = sorted(self._families.values(), key=lambda family: family.name)
            snapshot = [(family, dict(family.meters)) for family in families]
        return "".join(_exposition_of(family, meters) for family, meters in snapshot)

    def _meter(self, declared: _Family, tags: Tags | None, create: Callable[[], object]) -> object:
        key = _tag_values_of(tags or {})
        with self._lock:
            family = self._families.get(declared.name) or self._registered(declared)
            if family.kind != declared.kind:
                raise InvalidMeterError(f"{declared.name} is a {family.kind} already, not a {declared.kind}.")
            meter = family.meters.get(key)
            if meter is None:
                meter = create()
                family.meters[key] = meter
            return meter

    def _registered(self, family: _Family) -> _Family:
        if not _NAME.fullmatch(family.name):
            raise InvalidMeterError(
                f"{family.name!r} is no metric name Prometheus takes: letters, digits, underscores."
            )
        self._families[family.name] = family
        return family


def _tag_values_of(tags: Tags) -> _TagValues:
    for tag in tags:
        if not _TAG.fullmatch(tag) or tag == "le":
            raise InvalidMeterError(f"{tag!r} is no tag name Prometheus takes.")
    return tuple(sorted(tags.items()))


def _exposition_of(family: _Family, meters: Mapping[_TagValues, object]) -> str:
    name = f"{family.name}_total" if family.kind == "counter" else family.name
    lines = [f"# HELP {name} {_escaped_help(family.description)}", f"# TYPE {name} {family.kind}"]
    for tags, meter in sorted(meters.items()):
        lines.extend(_samples_of(name, tags, meter))
    return "\n".join(lines) + "\n"


def _samples_of(name: str, tags: _TagValues, meter: object) -> list[str]:
    if isinstance(meter, Counter):
        return [f"{name}{_labels(tags)} {_number(meter.value)}"]
    if isinstance(meter, Timer):
        buckets = [
            f"{name}_bucket{_labels((*tags, ('le', _number(bound))))} {_number(count)}"
            for bound, count in meter.cumulative()
        ]
        count = f"{name}_count{_labels(tags)} {_number(meter.count)}"
        return [*buckets, count, f"{name}_sum{_labels(tags)} {_number(meter.total_seconds)}"]
    return _gauge_sample(name, tags, meter)


def _gauge_sample(name: str, tags: _TagValues, read: object) -> list[str]:
    try:
        value = float(read()) if callable(read) else math.nan
    except Exception:  # a gauge that cannot be read is left out, not the whole scrape
        logger.debug("The gauge %s could not be read", name, exc_info=True)
        return []
    return [f"{name}{_labels(tags)} {_number(value)}"]


def _labels(tags: _TagValues) -> str:
    if not tags:
        return ""
    return "{" + ",".join(f'{tag}="{_escaped_value(value)}"' for tag, value in tags) + "}"


def _number(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    return "NaN" if math.isnan(value) else repr(float(value))


def _escaped_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _escaped_help(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n")
