import re
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Final, override

from wireup import injectable

_WORD_BOUNDARY: Final = re.compile(r"(?<!^)(?=[A-Z])")


class Status(StrEnum):
    """Whether a part of the application works, like Spring Boot's `Status`."""

    UP = "UP"
    DOWN = "DOWN"


class HealthIndicator(ABC):
    """A part the application needs, which `/health` checks, like a `HealthIndicator` bean in Spring Boot.

    Extend it and the subclass is a component of the container, registered as `HealthIndicator` under its own name,
    so its constructor receives sections and ports by type like any adapter. `check` raises when the part does not
    work. The bindings bring their own: the database with `[database]`, Redis with `[cache]`, RabbitMQ with
    `[rabbitmq]`.

        class PaymentGatewayHealthIndicator(HealthIndicator):
            def __init__(self, gateway: PaymentGatewayPort) -> None: ...

            @override
            def check(self) -> None:
                self._gateway.ping()          # raises when the gateway cannot be reached
    """

    @override
    def __init_subclass__(cls, *, component: bool = True, **kwargs: Any) -> None:
        """Registers a concrete subclass, qualified by its name so several can exist; `component=False` keeps a
        subclass out of the container, as a binding's own indicator that its provider registers."""
        super().__init_subclass__(**kwargs)
        if component and not getattr(cls.check, "__isabstractmethod__", False):
            injectable(cls, as_type=HealthIndicator, qualifier=f"{cls.__module__}.{cls.__qualname__}")

    @property
    def name(self) -> str:
        """The name of the part in `/health`: `payment_gateway` for `PaymentGatewayHealthIndicator`."""
        name = type(self).__name__.removesuffix("HealthIndicator") or type(self).__name__
        return _WORD_BOUNDARY.sub("_", name).lower()

    @abstractmethod
    def check(self) -> None:
        """Returns when the part works; raises when it does not, with what is wrong."""
