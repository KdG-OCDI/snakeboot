"""Technical library: one component scan for dependency injection and routing.

    @application_root                         # @SpringBootApplication: scan from this package down
    class MyApplication: ...

    ComponentScan.of(MyApplication).module_names()   # the modules of the container

Standard library only: it finds module names without importing them, so it works before the framework
underneath has started. Once it has, `classes_marked` and `methods_marked` find what decorators marked,
like Spring's `MethodIntrospector`.
"""

from snakeboot.component_scan.application_root import application_package, application_root
from snakeboot.component_scan.component_scan import (
    DEFAULT_EXCLUDE,
    SNAKEBOOT_AUTO_CONFIGURATION,
    ComponentScan,
    InvalidApplicationRootError,
    MarkedMethod,
)

__all__ = [
    "DEFAULT_EXCLUDE",
    "SNAKEBOOT_AUTO_CONFIGURATION",
    "ComponentScan",
    "InvalidApplicationRootError",
    "MarkedMethod",
    "application_package",
    "application_root",
]
