"""The tests find the application and the test components by reading the project's source, without configuration."""

import sys
from pathlib import Path

import pytest

from snakeboot.testing import ApplicationNotFoundError
from snakeboot.testing.source_scan import ProjectSources, source_roots

APPLICATION = """\
from snakeboot.component_scan import application_root


@application_root
class ShopApplication:
    '''Says in its docstring: @application_root and @test_component, which count for nothing.'''
"""

TEST_COMPONENT = """\
from snakeboot.testing import test_component


@test_component(replaces=object)
class Stub:
    pass
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_the_source_names_its_applications_and_the_modules_of_its_test_components(tmp_path: Path) -> None:
    write(tmp_path / "src" / "shop" / "shop_application.py", APPLICATION)
    write(tmp_path / "tests" / "doubles" / "stub.py", TEST_COMPONENT)
    write(tmp_path / "tests" / "test_shop.py", "# mentions @application_root in a comment only\n")

    sources = ProjectSources.scan([tmp_path / "src", tmp_path / "tests"])

    assert sources.applications == ("shop.shop_application:ShopApplication",)
    assert sources.test_component_modules == ("doubles.stub",)


NESTED_TEST_COMPONENTS = """\
from snakeboot.testing import application_test, test_component


@application_test
class TestShop:
    @test_component(replaces=object)
    class StubOfTheClass:
        pass


def test_shop() -> None:
    @test_component(replaces=object)
    class StubOfTheFunction:
        pass
"""

GUARDED_TEST_COMPONENT = """\
from snakeboot.testing import test_component

try:
    import shop
except ImportError:
    pass
else:
    @test_component(replaces=object)
    class Stub:
        pass
"""


def test_a_test_component_nested_in_a_class_or_a_function_is_none_of_the_project(tmp_path: Path) -> None:
    write(tmp_path / "test_shop.py", NESTED_TEST_COMPONENTS)

    assert ProjectSources.scan([tmp_path]).test_component_modules == ()


def test_a_test_component_in_a_block_of_the_module_is_one_of_the_project(tmp_path: Path) -> None:
    write(tmp_path / "doubles.py", GUARDED_TEST_COMPONENT)

    assert ProjectSources.scan([tmp_path]).test_component_modules == ("doubles",)


def test_a_file_under_two_roots_takes_its_name_from_the_deepest(tmp_path: Path) -> None:
    write(tmp_path / "src" / "shop" / "shop_application.py", APPLICATION)

    sources = ProjectSources.scan([tmp_path, tmp_path / "src"])

    assert sources.applications == ("shop.shop_application:ShopApplication",)


def test_hidden_directories_and_files_python_cannot_import_are_skipped(tmp_path: Path) -> None:
    write(tmp_path / ".venv" / "shop_application.py", APPLICATION)
    write(tmp_path / "my-scripts" / "shop_application.py", APPLICATION)
    write(tmp_path / "broken.py", "@application_root\nclass (:\n")

    assert ProjectSources.scan([tmp_path]) == ProjectSources((), ())


def test_the_one_application_is_imported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path / "scanned_shop" / "__init__.py", "")
    write(tmp_path / "scanned_shop" / "shop_application.py", APPLICATION)
    monkeypatch.syspath_prepend(tmp_path)

    application = ProjectSources.scan([tmp_path]).application()

    assert (application.__module__, application.__name__) == ("scanned_shop.shop_application", "ShopApplication")


@pytest.mark.parametrize("applications", [(), ("a:One", "b:Two")], ids=["none", "two"])
def test_no_application_or_two_ask_for_a_name(applications: tuple[str, ...]) -> None:
    with pytest.raises(ApplicationNotFoundError, match=r"name it with @application_test\(application=\.\.\.\)"):
        ProjectSources(applications, ()).application()


def test_the_roots_are_the_projects_own_directories_on_the_path() -> None:
    roots = source_roots()

    assert Path(sys.prefix).resolve() not in roots
    assert all("site-packages" not in root.parts for root in roots)
    assert Path("src").resolve() in roots  # snakeboot's own source, installed editable
