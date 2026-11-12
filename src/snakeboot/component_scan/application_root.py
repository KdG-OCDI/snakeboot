import sys
from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Final, overload

from snakeboot.component_scan.component_scan import (
    APPLICATION_ROOT_ATTRIBUTE,
    DEFAULT_EXCLUDE,
    ComponentScan,
    InvalidApplicationRootError,
)

_CLASS_INTERNALS: Final = frozenset({"__dict__", "__weakref__"})


@overload
def application_root[C: type](application_class: C, /) -> C: ...


@overload
def application_root[C: type](
    *,
    base_packages: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    default_exclude: tuple[str, ...] = DEFAULT_EXCLUDE,
) -> Callable[[C], C]: ...


def application_root[C: type](
    application_class: C | None = None,
    /,
    *,
    base_packages: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    default_exclude: tuple[str, ...] = DEFAULT_EXCLUDE,
) -> C | Callable[[C], C]:
    """Marks the root of the application, like Spring's `@SpringBootApplication`.

    By default the component scan starts in the package of the marked class and covers everything below it, so the
    class belongs in the top package (`myapp/myapp_application.py`). `base_packages` names the packages of the
    container instead, like `scanBasePackages`: an application that only assembles packages living elsewhere.
    Use it bare (`@application_root`) or with arguments (`@application_root(base_packages=(...), exclude=(...))`).
    `ComponentScan.of(...)` returns the scan.

    The package of the class is the application package, whatever `base_packages` says: the root of snakeboot's
    classpath, like `src/main/resources` in Spring Boot. It holds `application.toml` and the files of the profiles;
    `static/` and `templates/` are kept free there for pages. Migrations live next to their entities instead.
    """

    def declare(declared_class: C) -> C:
        packages = base_packages or (application_package(declared_class),)
        scan = ComponentScan(packages, exclude=exclude, default_exclude=default_exclude)
        setattr(declared_class, APPLICATION_ROOT_ATTRIBUTE, scan)
        return declared_class

    return declare if application_class is None else declare(application_class)


def application_package(application_class: type) -> str:
    """Returns the package of `application_class`: the top package of the application, next to its files."""
    module = sys.modules.get(application_class.__module__)
    if module is not None and hasattr(module, "__path__"):
        return module.__name__
    package, _, _ = application_class.__module__.rpartition(".")
    if not package:
        raise InvalidApplicationRootError(
            f"{application_class.__name__} is defined in {application_class.__module__!r}, outside any package; "
            "an application root lives in the top package of the application."
        )
    return package


def narrowed_application(application_class: type, excluded_modules: Iterable[str]) -> type:
    """Returns `application_class` without `excluded_modules`, as a test slice starts part of an application.

    The result is a subclass with the declarations of the application (its package, its configuration, its OpenAPI
    definition) and a component scan of its own: the same packages, with `excluded_modules` left out. Whatever asks
    the scan, the container, the REST API and the scheduler alike, sees only the rest.
    """
    scan = ComponentScan.of(application_class)
    namespace = {name: value for name, value in vars(application_class).items() if name not in _CLASS_INTERNALS}
    namespace[APPLICATION_ROOT_ATTRIBUTE] = replace(scan, exclude=(*scan.exclude, *excluded_modules))
    return type(application_class.__name__, (application_class,), namespace)
