import ast
import importlib
import importlib.util
import inspect
import pkgutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from types import ModuleType
from typing import Any, Final

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
class MarkedMethod[M]:
    """A method that a decorator marked, the class it belongs to, and what the decorator recorded on it.

    Spring finds `@RequestMapping`, `@RabbitListener` and `@Scheduled` methods with one helper,
    `MethodIntrospector.selectMethods`; `ComponentScan.methods_marked` plays that part here.
    """

    owner: type
    method: Callable[..., Any]
    mapping: M

    @property
    def name(self) -> str:
        """`module.Class.method`, for messages and a stable order."""
        return f"{self.owner.__module__}.{self.owner.__qualname__}.{self.method.__name__}"


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
    imports every file below it itself, past any exclusion; given only modules, wireup and
    `ControllerScan` look exactly where this scan points. Finding the names
    imports nothing, so settings can call it before Django has started. `classes_marked` and
    `methods_marked` do import the modules: they run once Django has started, to find what
    decorators marked (controllers, listeners, scheduled methods).
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
        scanned = self._scanned_files().keys()
        return sorted({name for name in (*scanned, *self.auto_configuration) if not self.is_excluded(name)})

    def app_configs(self) -> list[str]:
        """Returns the dotted path of every Django `AppConfig` declared under the base packages, sorted.

        Django takes such a path in INSTALLED_APPS. The scan reads the source and imports nothing, so settings can
        call it before Django has started: a class counts when its base is written `AppConfig` or `apps.AppConfig`.
        """
        return self.classes_extending("AppConfig")

    def models(self) -> list[str]:
        """Returns the dotted path of every Django model declared under the base packages, sorted.

        Read from the source like `app_configs`: a class counts when its base is written `Model` or `models.Model`.
        """
        return self.classes_extending("Model")

    def classes_extending(self, base: str) -> list[str]:
        """Returns the dotted path of every class under the base packages whose base is written `base`, sorted.

        `base` is a class name: `AppConfig` matches `class X(AppConfig)` and `class X(apps.AppConfig)`. Only the
        source is read, so a subclass of a subclass of `base` does not count.
        """
        return sorted(
            f"{module_name}.{declared}"
            for module_name, path in self._scanned_files().items()
            for declared in _classes_in(path, extending=base)
        )

    def classes_marked(self, marker: str) -> list[type]:
        """Imports the scanned modules and returns every class defined in them that carries `marker` itself.

        The marker is an attribute a class decorator set; an inherited one does not count. A class imported into
        another module is found once, where it is defined. Sorted by qualified name, so whatever is built from the
        result is always built in the same order.
        """
        return [candidate for candidate in self._classes() if marker in vars(candidate)]

    def methods_marked[M](self, marker: str, mapping_type: type[M]) -> list[MarkedMethod[M]]:
        """Imports the scanned modules and returns every method of their classes that a decorator marked.

        A method counts when its attribute `marker` holds a `mapping_type`, the record the decorator left.
        Sorted by `module.Class.method`.
        """
        found = [
            MarkedMethod(owner, method, mapping)
            for owner in self._classes()
            for _, method in inspect.getmembers(owner, inspect.isfunction)
            if isinstance(mapping := getattr(method, marker, None), mapping_type)
        ]
        return sorted(found, key=lambda marked: marked.name)

    def _classes(self) -> list[type]:
        modules = [importlib.import_module(name) for name in self.module_names()]
        found = {f"{owner.__module__}.{owner.__qualname__}": owner for owner in _classes_defined_in(modules)}
        return [found[name] for name in sorted(found)]

    def _scanned_files(self) -> dict[str, Path]:
        files = {name: path for package in self.base_packages for name, path in self._modules_under(package)}
        return {name: path for name, path in files.items() if not self.is_excluded(name)}

    def is_excluded(self, module_name: str) -> bool:
        """Tells whether a default or an own exclusion pattern matches the module or one of its parent packages.

        A pattern is a dotted name with `fnmatch` wildcards: `myapp.composition.django_project`
        excludes that package and everything below it, `*.migrations` every migrations package.
        """
        return any(
            fnmatchcase(module_name, pattern) or fnmatchcase(module_name, f"{pattern}.*")
            for pattern in (*self.default_exclude, *self.exclude)
        )

    def _modules_under(self, package_name: str) -> Iterator[tuple[str, Path]]:
        spec = importlib.util.find_spec(package_name)
        if spec is None:
            raise ModuleNotFoundError(
                f"The component scan cannot find the package {package_name!r}.", name=package_name
            )
        if spec.submodule_search_locations is None:
            yield package_name, Path(spec.origin or "")
            return
        for location in spec.submodule_search_locations:
            yield from self._modules_in_directory(Path(location), package_name)

    def _modules_in_directory(self, directory: Path, package_name: str) -> Iterator[tuple[str, Path]]:
        for module in pkgutil.iter_modules([str(directory)]):
            name = f"{package_name}.{module.name}"
            if module.ispkg:
                yield from self._modules_in_directory(directory / module.name, name)
            else:
                yield name, directory / f"{module.name}.py"


def _classes_defined_in(modules: list[ModuleType]) -> Iterator[type]:
    # vars(module) also holds what the module imported; only what it defines counts.
    for module in modules:
        for candidate in vars(module).values():
            if isinstance(candidate, type) and candidate.__module__ == module.__name__:
                yield candidate


def _classes_in(path: Path, *, extending: str) -> Iterator[str]:
    # Only the source is read: importing a models.py before Django has started fails.
    if path.suffix != ".py" or not path.is_file():
        return
    for node in ast.parse(path.read_text(encoding="utf-8"), filename=str(path)).body:
        if isinstance(node, ast.ClassDef) and extending in (_written_name(base) for base in node.bases):
            yield node.name


def _written_name(base: ast.expr) -> str:
    # `AppConfig` and `apps.AppConfig` both name the class AppConfig.
    if isinstance(base, ast.Attribute):
        return base.attr
    return base.id if isinstance(base, ast.Name) else ""
