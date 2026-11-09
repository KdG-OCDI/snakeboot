from collections.abc import Callable, Mapping
from dataclasses import replace
from importlib import import_module
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


class ApplicationContext(ApplicationComponents):
    """The running application, like Spring's `ApplicationContext`: its configuration, its container, its components.

    `of` reads the configuration and finds the modules of the application without building anything, so a command's
    `--help` answers at once; `refresh` imports the modules, reads every section they declare and builds wireup's
    container, like Spring's `refresh()`; `start` does both. With a `[database]` table, `refresh` installs the
    transaction manager of `@transactional` that the container provides.

    The context knows no framework: the binding that starts the application (`snakeboot.boot`) says which module
    joins the container for which table (`conditional`), and publishes the components it builds.
    """

    def __init__(self, application: type, scan: ComponentScan, configuration: Configuration) -> None:
        self.application = application
        self.scan = scan
        self.configuration = configuration
        self._container: SyncContainer | None = None

    @classmethod
    def of(cls, application: type, conditional: ConditionalModules) -> Self:
        """Reads the configuration of `application` and its modules, and configures logging; builds nothing yet."""
        package = application_package(application)
        configuration = begin_configuration(ServerProperties, optional=OPTIONAL_SECTIONS, package=package)
        logging_properties = (
            configuration.get(LoggingProperties) if LoggingProperties in configuration.sections else None
        )
        configure_logging(configuration.get(ServerProperties), logging_properties, service=package.rpartition(".")[2])
        present = tuple(
            module
            for section, modules in conditional.items()
            if section in configuration.sections
            for module in modules
        )
        scan = ComponentScan.of(application)
        scan = replace(scan, auto_configuration=(*scan.auto_configuration, *APPLICATION_AUTO_CONFIGURATION, *present))
        return cls(application, scan, configuration)

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

    def refresh(self, overrides: Mapping[Any, object] | None = None) -> None:
        """Imports the modules, reads every section they declare, builds the container and installs the transactions.

        `overrides` replace components before anything is built, as a test replaces a port with a double or the
        database with one in memory. A missing value, an unknown table or a dependency the container cannot satisfy
        stops the start here.
        """
        modules = [import_module(name) for name in self._module_names()]
        self.configuration.complete(*(section for module in modules for section in sections_declared_in(module)))
        self._container = wireup.create_sync_container(
            injectables=[
                *modules,
                wireup.instance(self, as_type=ApplicationComponents),
                wireup.instance(self, as_type=ApplicationContext),
            ],
            config={CONFIGURATION_KEY: self.configuration},
        )
        for component_type, replacement in (overrides or {}).items():
            self._container.override.set(component_type, replacement)
        if DatabaseProperties in self.configuration.sections:
            TransactionManagerRegistry.install(self.get(TransactionManager))

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

    def _module_names(self) -> list[str]:
        # The sections of snakeboot are declared outside the scan: their modules hold their providers.
        sections = (section.__module__ for section in self.configuration.sections)
        return list(dict.fromkeys([*self.scan.module_names(), *sections]))
