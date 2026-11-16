import inspect
from collections.abc import Callable
from typing import Any, overload

from wireup import injectable

from snakeboot.stereotype.stereotypes import InvalidComponentError


@overload
def bean[F: Callable[..., Any]](factory: F, /) -> F: ...
@overload
def bean[F: Callable[..., Any]](
    *, as_type: type[Any] | None = None, qualifier: str | None = None
) -> Callable[[F], F]: ...
def bean(factory: Any = None, /, *, as_type: type[Any] | None = None, qualifier: str | None = None) -> Any:
    """Declares a function that builds a component, like a `@Bean` method of a Spring `@Configuration`.

    For a component whose class the application does not own, or that takes more than a constructor call: a client
    of a library, an object built from a section. The function's parameters are its dependencies, by type, and its
    return annotation is the type others ask for; `as_type` names another, `qualifier` tells it apart from another
    component of the same type. The container calls it once, when the application starts, and hands that one object to
    everyone who asks.

    It registers a factory; it does not remember its calls. Calling the function yourself is a plain Python call, which
    builds a new object each time: like a `@Bean` method in Spring's lite mode (`proxyBeanMethods = false`), not one
    of a proxied `@Configuration`. A factory that needs another component takes it as a parameter, rather than calling
    that component's factory:

        @bean
        def http_client(properties: DownloadProperties) -> HttpClient: ...

        @bean
        def http_opener(client: HttpClient) -> OpenerDirector: ...
    """

    def declare(function: Any) -> Any:
        if inspect.isclass(function) or not callable(function):
            raise InvalidComponentError(
                f"@bean declares a function that builds a component, got {function!r}: a class is a @component."
            )
        return injectable(as_type=as_type, qualifier=qualifier)(function)

    return declare if factory is None else declare(factory)
