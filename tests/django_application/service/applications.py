"""Applications under test: each assembles another container around the files of this service."""

from snakeboot.component_scan import application_root


@application_root(base_packages=("tests.django_application.container",))
class ServiceApplication:
    """A container with one section, [greeting]."""


@application_root(base_packages=("tests.django_application.empty_container",))
class ServiceWithoutSectionsApplication:
    """A container that declares no section, although application.toml has [greeting]."""


@application_root(base_packages=("tests.django_application.container_with_a_model",))
class ServiceWithAModelApplication:
    """A container with a Django app that holds a model."""


@application_root(base_packages=("tests.django_application.container_with_a_loose_model",))
class ServiceWithALooseModelApplication:
    """A container with a model outside every app."""
