from snakeboot.component_scan import application_root


@application_root(base_packages=("tests.django_application.container",))
class ServiceWithOAuth2Application:
    """The container of ServiceApplication, with an application.toml that has [oauth2] and no [database]."""
