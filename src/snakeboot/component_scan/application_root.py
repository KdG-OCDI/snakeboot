import sys
from collections.abc import Callable
from typing import overload

from snakeboot.component_scan.component_scan import (
    APPLICATION_ROOT_ATTRIBUTE,
    DJANGO_ENTRY_POINTS,
    ComponentScan,
    InvalidApplicationRootError,
)


@overload
def application_root[C: type](application_class: C, /) -> C: ...


@overload
def application_root[C: type](
    *, exclude: tuple[str, ...] = (), default_exclude: tuple[str, ...] = DJANGO_ENTRY_POINTS
) -> Callable[[C], C]: ...


def application_root[C: type](
    application_class: C | None = None,
    /,
    *,
    exclude: tuple[str, ...] = (),
    default_exclude: tuple[str, ...] = DJANGO_ENTRY_POINTS,
) -> C | Callable[[C], C]:
    """Marks the root of the application, like Spring's `@SpringBootApplication`.

    The component scan starts in the package of the marked class and covers everything
    below it, so the class belongs in the top package (`myapp/myapp_application.py`).
    Use it bare (`@application_root`) or with own exclusions on top of the Django defaults
    (`@application_root(exclude=(...))`). Settings read the result with `ComponentScan.of(...)`.
    """

    def declare(declared_class: C) -> C:
        scan = ComponentScan((_package_of(declared_class),), exclude=exclude, default_exclude=default_exclude)
        setattr(declared_class, APPLICATION_ROOT_ATTRIBUTE, scan)
        return declared_class

    return declare if application_class is None else declare(application_class)


def _package_of(declared_class: type) -> str:
    module = sys.modules.get(declared_class.__module__)
    if module is not None and hasattr(module, "__path__"):
        return module.__name__
    package, _, _ = declared_class.__module__.rpartition(".")
    if not package:
        raise InvalidApplicationRootError(
            f"{declared_class.__name__} is defined in {declared_class.__module__!r}, outside any package; "
            "an application root lives in the top package it scans."
        )
    return package
