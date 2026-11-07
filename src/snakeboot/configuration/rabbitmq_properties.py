from pydantic import SecretStr

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


class RabbitListenerProperties(Section):
    """The table `[rabbitmq.listener]`, like `spring.rabbitmq.listener.simple.*`.

    `auto_startup = false` keeps this process from consuming, for a web process whose listeners run in a process of
    their own (`run_lifecycle`).
    """

    auto_startup: bool


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
    """

    host: str
    port: int
    username: str
    password: SecretStr
    virtual_host: str
    listener: RabbitListenerProperties
