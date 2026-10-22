import importlib
import pkgutil
from collections.abc import Iterable
from types import ModuleType

from snakeboot.rest.rest_controller_mappings import CONTROLLER_MAPPING_ATTRIBUTE


class RestControllerScanner:
    """Component scan: finds every class with a REST marker in the modules under some packages.

    Python has no classpath scanning and a decorator only runs when its module is
    imported, so a registry filled by decorators would silently miss controllers in
    modules nobody imported. The scanner imports the modules itself, which makes the
    result complete and independent of import order. It is sorted, so routes are
    always registered in the same order.
    """

    def scan(self, packages: Iterable[str | ModuleType], *, marker: str = CONTROLLER_MAPPING_ATTRIBUTE) -> list[type]:
        """Returns the classes carrying `marker` (controllers by default) defined in `packages`.

        `packages` may name packages (searched with their subpackages) or plain modules, or be
        module objects: the same forms wireup accepts, so the list in `settings.WIREUP` fits.
        """
        found: dict[str, type] = {}
        for package in packages:
            imported = package if isinstance(package, ModuleType) else importlib.import_module(package)
            for module in self._modules_under(imported):
                for candidate in vars(module).values():
                    if self._is_marked_class_defined_in(candidate, module, marker):
                        found[f"{candidate.__module__}.{candidate.__qualname__}"] = candidate
        return [found[name] for name in sorted(found)]

    def _modules_under(self, package: ModuleType) -> list[ModuleType]:
        if not hasattr(package, "__path__"):
            return [package]
        submodules = pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}.")
        return [package, *(importlib.import_module(info.name) for info in submodules)]

    def _is_marked_class_defined_in(self, candidate: object, module: ModuleType, marker: str) -> bool:
        # A class imported into another module is found once, where it is defined.
        return isinstance(candidate, type) and marker in vars(candidate) and candidate.__module__ == module.__name__
