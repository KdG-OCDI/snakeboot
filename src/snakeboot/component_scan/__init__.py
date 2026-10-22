"""Technical library: one component scan for dependency injection and routing.

    @application_root                         # @SpringBootApplication: scan from this package down
    class MyApplication: ...

    # in settings.py, inside the setting wireup needs anyway:
    WIREUP = WireupSettings(injectables=[*ComponentScan.of(MyApplication).module_names()])

Standard library only: it finds module names without importing them, so settings can use it
before Django has started.
"""

from snakeboot.component_scan.application_root import application_root
from snakeboot.component_scan.component_scan import (
    DJANGO_ENTRY_POINTS,
    SNAKEBOOT_AUTO_CONFIGURATION,
    ComponentScan,
    InvalidApplicationRootError,
)

__all__ = [
    "DJANGO_ENTRY_POINTS",
    "SNAKEBOOT_AUTO_CONFIGURATION",
    "ComponentScan",
    "InvalidApplicationRootError",
    "application_root",
]
