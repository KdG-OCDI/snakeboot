import importlib.util
import pkgutil
from collections.abc import Iterator
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Final

DJANGO_ENTRY_POINTS: Final = ("*.wsgi", "*.asgi", "*.migrations")
"""Modules every Django project has that are never components.

`wsgi.py` and `asgi.py` start Django when they are imported; a scan that imported them
during start-up would start Django a second time, which Django refuses. Migrations hold
no components. These are conventions of Django, so the scan needs no Django import to know them.
"""

SNAKEBOOT_AUTO_CONFIGURATION: Final = ("snakeboot.events.application_event_publisher_injectable",)
"""Modules of snakeboot itself that register components, like Spring Boot's `@EnableAutoConfiguration`.

Spring Boot always provides an `ApplicationEventPublisher`; so does snakeboot, through this
module. The scan adds it to every application without the application naming it. The names
are strings: the scan still imports nothing and depends on no other part of snakeboot.
"""

APPLICATION_ROOT_ATTRIBUTE: Final = "__component_scan__"


class InvalidApplicationRootError(TypeError):
    """Raised at start-up when a class cannot be, or is not, the root of a component scan.

    The application root decides what the application is made of; a wrong one must stop
    the start-up instead of silently scanning nothing.
    """


@dataclass(frozen=True, slots=True)
class ComponentScan:
    """Which modules make up the application, like `@ComponentScan(basePackages, excludeFilters)` in Spring.

    Spring Boot scans from the package of the `@SpringBootApplication` class downwards and
    skips what is never a component through its default filters. Here the base packages are
    named, `default_exclude` skips Django's entry points, and `exclude` adds the application's
    own exclusions (rarely needed). `default_exclude=()` turns the defaults off, like Spring's
    `useDefaultFilters = false`. `auto_configuration` adds the modules through which snakeboot
    registers its own components; an exclusion pattern can remove one, `auto_configuration=()`
    removes them all.

    `module_names()` lists plain modules only, never packages. Given a package, wireup
    and the controller scanner import every file below it themselves, past any exclusion;
    given only modules, both look exactly where this scan points. Finding the names
    imports nothing, so settings can call it before Django has started.
    """

    base_packages: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    default_exclude: tuple[str, ...] = DJANGO_ENTRY_POINTS
    auto_configuration: tuple[str, ...] = SNAKEBOOT_AUTO_CONFIGURATION

    @classmethod
    def of(cls, application_class: type) -> "ComponentScan":
        """Returns the scan that `@application_root` declared on `application_class`."""
        scan = vars(application_class).get(APPLICATION_ROOT_ATTRIBUTE)
        if not isinstance(scan, ComponentScan):
            raise InvalidApplicationRootError(f"{application_class.__name__} is not an @application_root.")
        return scan

    def module_names(self) -> list[str]:
        """Returns the dotted names of every module under the base packages, plus the auto-configuration, sorted.

        Excluded modules are left out, auto-configuration included.
        """
        scanned = (name for base_package in self.base_packages for name in self._modules_under(base_package))
        return sorted({name for name in (*scanned, *self.auto_configuration) if not self.is_excluded(name)})

    def is_excluded(self, module_name: str) -> bool:
        """Tells whether a default or an own exclusion pattern matches the module or one of its parent packages.

        A pattern is a dotted name with `fnmatch` wildcards: `myapp.composition.django_project`
        excludes that package and everything below it, `*.migrations` every migrations package.
        """
        return any(
            fnmatchcase(module_name, pattern) or fnmatchcase(module_name, f"{pattern}.*")
            for pattern in (*self.default_exclude, *self.exclude)
        )

    def _modules_under(self, package_name: str) -> Iterator[str]:
        spec = importlib.util.find_spec(package_name)
        if spec is None:
            raise ModuleNotFoundError(
                f"The component scan cannot find the package {package_name!r}.", name=package_name
            )
        if spec.submodule_search_locations is None:
            yield package_name
            return
        for location in spec.submodule_search_locations:
            yield from self._modules_in_directory(Path(location), package_name)

    def _modules_in_directory(self, directory: Path, package_name: str) -> Iterator[str]:
        for module in pkgutil.iter_modules([str(directory)]):
            name = f"{package_name}.{module.name}"
            if module.ispkg:
                yield from self._modules_in_directory(directory / module.name, name)
            else:
                yield name
