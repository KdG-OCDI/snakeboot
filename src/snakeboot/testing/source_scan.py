import ast
import os
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Final

from snakeboot.testing.component_replacements import replacing_components
from snakeboot.testing.declared_classes import decorator_names_of, module_name_of

APPLICATION_ROOT: Final = "application_root"
TEST_COMPONENT: Final = "test_component"
_SKIPPED_DIRECTORIES: Final = frozenset({"__pycache__", "site-packages", "node_modules"})


class ApplicationNotFoundError(LookupError):
    """Raised when an `@application_test` names no application and the source holds none, or more than one."""


@dataclass(frozen=True, slots=True)
class ProjectSources:
    """What the project's own source declares for its tests: its applications and its test components.

    Spring Boot finds the `@SpringBootConfiguration` by searching the packages above a test. A Python project keeps
    its tests apart from its packages, so snakeboot reads the source on Python's path instead: the directories of
    the project's own code, which an editable install, pytest's `pythonpath` and the folder of the tests put there,
    and never an environment's `site-packages`. It reads the files without importing them, as `declared_classes`
    does, and imports only the modules with a `@test_component`.
    """

    applications: tuple[str, ...]
    test_component_modules: tuple[str, ...]

    @classmethod
    def scan(cls, roots: Iterable[Path] | None = None) -> "ProjectSources":
        """Reads the source under `roots`, by default the project's directories on `sys.path`."""
        applications: list[str] = []
        modules: list[str] = []
        for module, source in _modules_under(source_roots() if roots is None else roots):
            for node in ast.walk(source):
                if isinstance(node, ast.ClassDef):
                    decorators = decorator_names_of(node)
                    applications += [f"{module}:{node.name}"] if APPLICATION_ROOT in decorators else []
                    modules += [module] if TEST_COMPONENT in decorators else []
        return cls(tuple(applications), tuple(dict.fromkeys(modules)))

    def application(self) -> type:
        """Imports and returns the one application of the project; none or several stop the test."""
        if len(self.applications) != 1:
            found = ", ".join(self.applications) or "none"
            raise ApplicationNotFoundError(
                f"An @application_test without an application starts the one @application_root of the project's "
                f"source, and found {len(self.applications)} ({found}): name it with "
                "@application_test(application=...)."
            )
        module, _, name = self.applications[0].partition(":")
        application = getattr(import_module(module), name)
        if not isinstance(application, type):
            raise ApplicationNotFoundError(f"{self.applications[0]} is no class.")
        return application

    def test_components(self) -> Mapping[Any, type]:
        """Imports the modules with a `@test_component` and returns every test component, by what it replaces."""
        for module in self.test_component_modules:
            import_module(module)
        return replacing_components()


def source_roots() -> list[Path]:
    """Returns the directories on `sys.path` that hold the project's own source, not an environment's packages."""
    environments = {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}
    roots: list[Path] = []
    for entry in sys.path:
        path = Path(entry or os.curdir).resolve()
        inside_an_environment = any(path == e or e in path.parents for e in environments)
        if path.is_dir() and not inside_an_environment and "site-packages" not in path.parts:
            roots.append(path)
    return list(dict.fromkeys(roots))


def _modules_under(roots: Iterable[Path]) -> Iterator[tuple[str, ast.Module]]:
    # A file under two roots is imported by the name the deepest one gives it.
    root_of: dict[Path, Path] = {}
    for root in sorted(roots, key=lambda directory: len(directory.parts)):
        root_of |= dict.fromkeys(_python_files(root), root)
    markers = (f"@{APPLICATION_ROOT}", f"@{TEST_COMPONENT}")
    for path, root in sorted(root_of.items()):
        module = module_name_of(path, root)
        text = path.read_text(encoding="utf-8", errors="replace")
        if all(part.isidentifier() for part in module.split(".")) and any(marker in text for marker in markers):
            try:
                yield module, ast.parse(text)
            except SyntaxError:
                continue


def _python_files(root: Path) -> Iterator[Path]:
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if not d.startswith(".") and d not in _SKIPPED_DIRECTORIES]
        yield from (Path(directory) / name for name in files if name.endswith(".py"))
