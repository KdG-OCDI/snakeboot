import ast
from pathlib import Path


def declared_classes(package_directory: Path, decorator_name: str) -> set[str]:
    """Returns `module.Class` for every class in the source under `package_directory` carrying `decorator_name`.

    It reads the source instead of importing it, so an architecture test can compare what is
    *written* with what the component scan *found*: a `@rest_controller` in a module the scan
    skips would otherwise be silently missing from the API. Both `@name` and `@name(...)` count.
    """
    found: set[str] = set()
    for path in sorted(package_directory.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and any(_names(d, decorator_name) for d in node.decorator_list):
                found.add(f"{_module_name(package_directory, path)}.{node.name}")
    return found


def qualified_names(classes: list[type]) -> set[str]:
    """Returns `module.Class` for each class, the form `declared_classes` uses."""
    return {f"{cls.__module__}.{cls.__qualname__}" for cls in classes}


def _names(decorator: ast.expr, decorator_name: str) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return isinstance(target, ast.Name) and target.id == decorator_name


def _module_name(package_directory: Path, path: Path) -> str:
    relative = path.relative_to(package_directory.parent).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join(parts)
