from datetime import timedelta
from typing import Any, Self

from pydantic import SecretStr, model_validator

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


class RabbitListenerRetryProperties(Section):
    """The optional table `[rabbitmq.listener.retry]`, like `spring.rabbitmq.listener.simple.retry.*`.

    How often a message whose handling fails is tried, and how long a listener waits between two attempts: the first
    pause is `initial_interval`, each next one `multiplier` times longer, none longer than `max_interval`. A time is a
    number of seconds or an ISO 8601 duration ("PT30S"). Without the table, a message is tried three times, a second
    apart, as with Spring Boot's defaults.

        [rabbitmq.listener.retry]
        max_attempts = 6                # then the message is refused for good
        initial_interval = 2            # 2 s, 4 s, 8 s, 16 s, 30 s: about a minute in all
        multiplier = 2
        max_interval = 30
    """

    max_attempts: int
    initial_interval: timedelta
    multiplier: float
    max_interval: timedelta

    @model_validator(mode="after")
    def _refuse_a_back_off_that_cannot_work(self) -> Self:
        if self.max_attempts < 1 or self.initial_interval < timedelta(0) or self.multiplier < 1:
            raise ValueError(
                "[rabbitmq.listener.retry] needs one attempt at least, an initial_interval that is not negative and "
                "a multiplier of 1 or more."
            )
        if self.max_interval < self.initial_interval:
            raise ValueError("[rabbitmq.listener.retry] needs a max_interval no shorter than its initial_interval.")
        return self


class RabbitListenerProperties(Section):
    """The table `[rabbitmq.listener]`, like `spring.rabbitmq.listener.simple.*`.

    `auto_startup = false` keeps this process from consuming, for a web process whose listeners run in a process of
    their own (`run_lifecycle`). The table `[rabbitmq.listener.retry]` may follow; without it, `retry` reads as None
    and a failing message is tried three times, a second apart.
    """

    auto_startup: bool
    retry: RabbitListenerRetryProperties | None

    @model_validator(mode="before")
    @classmethod
    def _without_a_retry_table(cls, table: Any) -> Any:
        # A profile and the environment change keys and cannot write None: a missing table reads as None.
        return {"retry": None, **table} if isinstance(table, dict) else table


@configuration_properties("rabbitmq")
class RabbitProperties(Section):
    """The optional section `[rabbitmq]`: the broker of `@rabbit_listener` methods and the `RabbitTemplate`.

    Like `spring.rabbitmq.*`. Without the section, the application has neither; the password usually comes from the
    environment of the container (RABBITMQ__PASSWORD).

        [rabbitmq]
        host = "rabbitmq"
        port = 5672
        username = "guest"
        virtual_host = "/"

        [rabbitmq.listener]
        auto_startup = true

        [rabbitmq.listener.retry]       # optional: three attempts, a second apart, without it
        max_attempts = 6
        initial_interval = 2
        multiplier = 2
        max_interval = 30
    """

    host: str
    port: int
    username: str
    password: SecretStr
    virtual_host: str
    listener: RabbitListenerProperties
