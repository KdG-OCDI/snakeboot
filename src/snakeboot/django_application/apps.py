from typing import override

from django.apps import AppConfig
from django.conf import settings

from snakeboot.django_application.container_sections import complete_configuration


class DjangoApplicationConfig(AppConfig):
    """Reads the sections of the container when Django starts; `configure_django` puts this app in INSTALLED_APPS."""

    name = "snakeboot.django_application"
    label = "snakeboot_django_application"
    verbose_name = "snakeboot"

    @override
    def ready(self) -> None:
        complete_configuration(settings)
