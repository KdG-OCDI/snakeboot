from abc import ABC, abstractmethod
from typing import Any, ClassVar, override

from wireup import injectable


class Lifecycle(ABC):
    """A component that starts with the application and stops with it, like Spring's `SmartLifecycle`.

    Extend it and the subclass is a component of the container, registered as `Lifecycle` under its own name, so its
    constructor receives sections and ports by type like any adapter. `ApplicationLifecycle` starts every one when
    the server starts (uvicorn's lifespan, or `run_lifecycle` without a web server), in ascending `phase`, and stops
    them in the reverse order. A management command such as `migrate` starts none.

        class Heartbeat(Lifecycle):
            def __init__(self, clock: ClockPort) -> None: ...

            @override
            def start(self) -> None: ...  # start a thread, open a connection; return quickly

            @override
            def stop(self) -> None: ...  # finish what is in hand, then let go
    """

    phase: ClassVar[int] = 0
    """Lower phases start first and stop last, like `SmartLifecycle.getPhase()`."""

    @override
    def __init_subclass__(cls, *, component: bool = True, **kwargs: Any) -> None:
        """Registers a concrete subclass, qualified by its name so several can exist; `component=False` keeps a
        subclass out of the container, as a base meant to be extended."""
        super().__init_subclass__(**kwargs)
        # ABCMeta computes __abstractmethods__ only after this hook, so ask the methods themselves.
        still_abstract = any(getattr(getattr(cls, name), "__isabstractmethod__", False) for name in ("start", "stop"))
        if component and not still_abstract:
            injectable(cls, as_type=Lifecycle, qualifier=f"{cls.__module__}.{cls.__qualname__}")

    @abstractmethod
    def start(self) -> None:
        """Starts the component; a failure stops the start-up of the application."""

    @abstractmethod
    def stop(self) -> None:
        """Stops the component; called once, after a successful `start`."""
