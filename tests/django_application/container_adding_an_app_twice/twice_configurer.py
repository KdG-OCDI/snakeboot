from snakeboot.django_application import DjangoConfigurer


class TwiceConfigurer(DjangoConfigurer):
    """Adds an app that the component scan finds already."""

    installed_apps = ("tests.django_application.container_with_a_model.persistence",)
