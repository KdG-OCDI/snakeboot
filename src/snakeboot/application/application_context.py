import inspect
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import replace
from importlib import import_module
from types import FunctionType, ModuleType
from typing import Any, Final, Self, override

import wireup
from wireup import SyncContainer
from wireup.errors import WireupError

from snakeboot.application.logging_configuration import configure_logging
from snakeboot.component_scan import ComponentScan, MarkedMethod, application_package
from snakeboot.configuration import (
    CONFIGURATION_KEY,
    CacheProperties,
    Configuration,
    CorsProperties,
    DatabaseProperties,
    EventsProperties,
    LoggingProperties,
    OAuth2Properties,
    RabbitProperties,
    SchedulingProperties,
    Section,
    ServerProperties,
    begin_configuration,
    sections_declared_in,
)
from snakeboot.events.event_listener_method_processor import EventListenerMethodProcessor
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.transaction import TransactionManager, TransactionManagerRegistry

APPLICATION_AUTO_CONFIGURATION: Final = (
    "snakeboot.application.background_work",
    "snakeboot.application.run_lifecycle_command",
)
"""Modules of snakeboot that every application's container holds: what background threads need, `run_lifecycle`."""

OPTIONAL_SECTIONS: Final = (
    DatabaseProperties,
    CacheProperties,
    OAuth2Properties,
    RabbitProperties,
    SchedulingProperties,
    CorsProperties,
    LoggingProperties,
    EventsProperties,
)
"""The sections of snakeboot an application may leave out; `[server]` is the one it always has."""

type ConditionalModules = Mapping[type[Section], tuple[str, ...]]
"""Which modules join the container when the configuration has which table, like `@ConditionalOnProperty`."""


def component_scan_of(
    application: type, conditional: ConditionalModules, present: Collection[type[Section]]
) -> ComponentScan:
    """Returns the component scan of `application`: its modules, snakeboot's own, and those of the tables `present`.

    `ApplicationContext.of` passes the sections it read. The help of the program passes the sections whose table the
    configuration has, without reading a value, so it lists the same commands when a value is missing or invalid.
    """
    conditional_modules = tuple(
        module for section, modules in conditional.items() if section in present for module in modules
    )
    scan = ComponentScan.of(application)
    return replace(
        scan, auto_configuration=(*scan.auto_configuration, *APPLICATION_AUTO_CONFIGURATION, *conditional_modules)
    )


class ApplicationContext(ApplicationComponents):
    """The running application, like Spring's `ApplicationContext`: its configuration, its container, its components.

    `of` reads the configuration and finds the modules of the application without building anything; `refresh`
    imports the modules, reads every section they declare and builds wireup's container, like Spring's `refresh()`;
    `start` does both. With a `[database]` table, `refresh` installs the transaction manager of `@transactional` that
    the container provides; then it builds every event listener and registers it with the publisher, so a listener
    may depend on a use case that publishes events.

    The context knows no framework: the binding that starts the application (`snakeboot.boot`) says which module
    joins the container for which table (`conditional`), and publishes the components it builds.
    """

    def __init__(self, application: type, scan: ComponentScan, configuration: Configuration) -> None:
        self.application = application
        self.scan = scan
        self.configuration = configuration
        self._container: SyncContainer | None = None

    @classmethod
    def of(
        cls,
        application: type,
        conditional: ConditionalModules,
        *,
        profile: str | None = None,
        properties: Mapping[str, object] | None = None,
    ) -> Self:
        """Reads the configuration of `application` and its modules, and configures logging; builds nothing yet.

        A test may activate a `profile` and set `properties` that win over the files and the environment.
        """
        package = application_package(application)
        configuration = begin_configuration(
            ServerProperties, optional=OPTIONAL_SECTIONS, package=package, profile=profile, properties=properties
        )
        logging_properties = (
            configuration.get(LoggingProperties) if LoggingProperties in configuration.sections else None
        )
        configure_logging(configuration.get(ServerProperties), logging_properties, service=package.rpartition(".")[2])
        return cls(application, component_scan_of(application, conditional, configuration.sections), configuration)

    @classmethod
    def start(cls, application: type, conditional: ConditionalModules) -> Self:
        """Reads the configuration and builds the container of `application`: `of`, then `refresh`."""
        context = cls.of(application, conditional)
        context.refresh()
        return context

    @property
    def started(self) -> bool:
        """Tells whether `refresh` built the container."""
        return self._container is not None

    def refresh(
        self,
        overrides: Mapping[Any, object] | None = None,
        *,
        additions: Sequence[object] = (),
        prepare: Callable[[Self], None] | None = None,
    ) -> None:
        """Imports the modules, reads every section they declare, builds the container, installs the transactions and
        registers the event listeners.

        `overrides` replace components before anything is built, as a test replaces a port with a double or the
        database with one in memory. `additions` are wireup's injectables that join the container besides the
        modules, as a test adds a listener that records every event. `prepare` runs on the built container before the
        listeners are built, like Spring's `BeanFactoryPostProcessor`, as a test replaces the components it finds
        there. Then every `@application_event_listener` is built and registered with the publisher, like Spring's
        `EventListenerMethodProcessor` once every singleton exists. A missing value, an unknown table, a dependency
        the container cannot satisfy or a listener that cannot be built stops the start here, and closes the context.
        """
        modules = [import_module(name) for name in self._module_names()]
        self.configuration.complete(*(section for module in modules for section in sections_declared_in(module)))
        self._container = wireup.create_sync_container(
            injectables=[
                *(self._registrable_part_of(module) for module in modules),
                *additions,
                wireup.instance(self, as_type=ApplicationComponents),
                wireup.instance(self, as_type=ApplicationContext),
            ],
            config={CONFIGURATION_KEY: self.configuration},
        )
        try:
            self._finish_refresh(overrides or {}, prepare)
        except BaseException:
            self.close()
            raise

    def replace_component(self, component_type: Any, replacement: object) -> None:
        """Replaces the component of `component_type` in the built container, as a test replaces a port with a double.

        Components built before keep what they were given, so a test replaces a component before it is first used.
        A type the container does not have stops the start: there is nothing to replace.
        """
        name = getattr(component_type, "__qualname__", repr(component_type))
        if self._container is None:
            raise LookupError(f"The application is not started yet: refresh() builds the {name} to replace.")
        try:
            self._container.override.set(component_type, replacement)
        except WireupError as error:
            raise LookupError(f"The container has no {name} to replace: {error}") from error

    def close(self) -> None:
        """Closes the container, which releases what its components hold (the database's connections, for one)."""
        if self._container is not None:
            self._container.close()
            self._container = None
            TransactionManagerRegistry.uninstall()

    @override
    def classes_marked(self, marker: str) -> list[type]:
        return self.scan.classes_marked(marker)

    @override
    def methods_marked[M](self, marker: str, mapping_type: type[M]) -> list[MarkedMethod[M]]:
        return self.scan.methods_marked(marker, mapping_type)

    @override
    def get[T](self, component_type: Callable[..., T]) -> T:
        name = getattr(component_type, "__qualname__", repr(component_type))
        if self._container is None:
            raise LookupError(f"The application is not started yet: refresh() builds the {name}.")
        try:
            component: T = self._container.get(component_type)
        except WireupError as error:
            raise LookupError(f"The container has no {name}: {error}") from error
        return component

    def _finish_refresh(self, overrides: Mapping[Any, object], prepare: Callable[[Self], None] | None) -> None:
        for component_type, replacement in overrides.items():
            self.replace_component(component_type, replacement)
        if DatabaseProperties in self.configuration.sections:
            TransactionManagerRegistry.install(self.get(TransactionManager))
        if prepare is not None:
            prepare(self)
        self._register_listeners()

    def _register_listeners(self) -> None:
        # The publisher depends on no listener, so a listener may inject a use case that publishes; building them all
        # here, while the application starts, stops it on a listener that cannot be built instead of the first event.
        try:
            processor = self.get(EventListenerMethodProcessor)
        except Exception as error:
            error.add_note("Raised while the application started and built its event listeners.")
            raise
        processor.register_listeners()

    def _module_names(self) -> list[str]:
        # The sections of snakeboot are declared outside the scan: their modules hold their providers.
        sections = (section.__module__ for section in self.configuration.sections)
        return list(dict.fromkeys([*self.scan.module_names(), *sections]))

    def _registrable_part_of(self, module: ModuleType) -> ModuleType:
        """`module` as wireup reads it: without what it imported from a module the scan leaves out.

        wireup registers every component among a module's members, the ones it imported too. A controller that
        imports its use case would otherwise bring it into an application, or a test slice, whose scan excludes it.
        """
        imported = {name for name, member in vars(module).items() if self._defined_outside_the_scan(member)}
        if not imported:
            return module
        part = ModuleType(module.__name__)
        part.__dict__.update({name: member for name, member in vars(module).items() if name not in imported})
        return part

    def _defined_outside_the_scan(self, member: object) -> bool:
        is_declaration = inspect.isclass(member) or isinstance(member, FunctionType)
        return is_declaration and self.scan.is_excluded(getattr(member, "__module__", "") or "")
