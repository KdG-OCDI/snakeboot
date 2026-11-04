from snakeboot.component_scan import application_root


@application_root(base_packages=("tests.django_application.container_with_a_configurer",))
class ConfiguredApplication:
    """A container with a configurer, in a package with one of its own."""


@application_root(
    base_packages=(
        "tests.django_application.container_with_a_model",
        "tests.django_application.container_adding_an_app_twice",
    )
)
class AppAddedTwiceApplication:
    """A container whose configurer adds an app that the scan finds already."""
