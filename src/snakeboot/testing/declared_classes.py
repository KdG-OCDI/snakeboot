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
            if isinstance(node, ast.ClassDef) and decorator_name in decorator_names_of(node):
                found.add(f"{module_name_of(path, package_directory.parent)}.{node.name}")
    return found


def qualified_names(classes: list[type]) -> set[str]:
    """Returns `module.Class` for each class, the form `declared_classes` uses."""
    return {f"{cls.__module__}.{cls.__qualname__}" for cls in classes}


def decorator_names_of(node: ast.ClassDef) -> set[str]:
    """Returns the names of the decorators of a class in the source: `name` for both `@name` and `@name(...)`."""
    targets = (decorator.func if isinstance(decorator, ast.Call) else decorator for decorator in node.decorator_list)
    return {target.id for target in targets if isinstance(target, ast.Name)}


def module_name_of(path: Path, root: Path) -> str:
    """Returns the name under which Python imports the file `path` from the directory `root` on its path."""
    relative = path.relative_to(root).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join(parts)
