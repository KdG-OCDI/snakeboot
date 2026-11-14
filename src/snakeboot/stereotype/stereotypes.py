from collections.abc import Callable
from enum import StrEnum
from typing import Any, Final, overload

from wireup import injectable

STEREOTYPE_ATTRIBUTE: Final = "__snakeboot_stereotype__"
"""The mark a stereotype leaves on its class: the `Stereotype` it declared, which `ComponentScan.classes_marked`
finds."""


class Stereotype(StrEnum):
    """What a component is in the application, like the annotations of `org.springframework.stereotype`."""

    COMPONENT = "component"
    """Any component of the container: `@component`."""
    SERVICE = "service"
    """A use case or a service of the application layer: `@service`."""
    REPOSITORY = "repository"
    """An adapter that keeps and finds the objects of the domain: `@repository`."""


class InvalidComponentError(TypeError):
    """Raised when a class or a function cannot be the component its decorator declares.

    Like a broken controller, it stops the application when its module is imported, not at the first call.
    """


@overload
def component[C: type](component_class: C, /) -> C: ...
@overload
def component[C: type](*, as_type: type[Any] | None = None, qualifier: str | None = None) -> Callable[[C], C]: ...
def component(component_class: Any = None, /, *, as_type: type[Any] | None = None, qualifier: str | None = None) -> Any:
    """Declares a component of the container, like Spring's `@Component`.

    The class is created once, its constructor receives its dependencies by type, and the application refuses to
    start when one is missing. `as_type` names the port (an abstract class or a Protocol) under which others ask for
    it, as a Spring bean is found by the interface it implements; `qualifier` tells it apart from another component
    of the same type, like `@Qualifier`. A class that does not extend the abstract class `as_type` names is refused.
    """
    return _declared(Stereotype.COMPONENT, component_class, as_type=as_type, qualifier=qualifier)


@overload
def service[C: type](service_class: C, /) -> C: ...
@overload
def service[C: type](*, as_type: type[Any] | None = None, qualifier: str | None = None) -> Callable[[C], C]: ...
def service(service_class: Any = None, /, *, as_type: type[Any] | None = None, qualifier: str | None = None) -> Any:
    """Declares a use case or a service of the application layer, like Spring's `@Service`.

    It is a `@component` by another name: the name tells the reader, and an architecture test, what the class is.
    """
    return _declared(Stereotype.SERVICE, service_class, as_type=as_type, qualifier=qualifier)


@overload
def repository[C: type](repository_class: C, /) -> C: ...
@overload
def repository[C: type](*, as_type: type[Any] | None = None, qualifier: str | None = None) -> Callable[[C], C]: ...
def repository(
    repository_class: Any = None, /, *, as_type: type[Any] | None = None, qualifier: str | None = None
) -> Any:
    """Declares an adapter that keeps and finds the objects of the domain, like Spring's `@Repository`.

    It is a `@component` by another name, for the class that implements a repository port of the application. An
    interface that extends `CrudRepository` needs none: snakeboot implements it and that implementation is its
    component.
    """
    return _declared(Stereotype.REPOSITORY, repository_class, as_type=as_type, qualifier=qualifier)


def stereotype_of(component_class: type) -> Stereotype | None:
    """Returns the stereotype `component_class` declared itself, or None; an inherited one does not count."""
    declared = vars(component_class).get(STEREOTYPE_ATTRIBUTE)
    return declared if isinstance(declared, Stereotype) else None


def _declared(stereotype: Stereotype, target: Any, *, as_type: type[Any] | None, qualifier: str | None) -> Any:
    def declare(component_class: Any) -> Any:
        _check(stereotype, component_class, as_type)
        setattr(component_class, STEREOTYPE_ATTRIBUTE, stereotype)
        return injectable(as_type=as_type, qualifier=qualifier)(component_class)

    return declare if target is None else declare(target)


def _check(stereotype: Stereotype, component_class: Any, as_type: type[Any] | None) -> None:
    if not isinstance(component_class, type):
        raise InvalidComponentError(
            f"@{stereotype} declares a class, got {component_class!r}: a function that builds a component is a @bean."
        )
    is_protocol = getattr(as_type, "_is_protocol", False)
    if as_type is not None and not is_protocol and not issubclass(component_class, as_type):
        raise InvalidComponentError(
            f"{component_class.__qualname__} is declared as_type={as_type.__qualname__}, which it does not extend."
        )
