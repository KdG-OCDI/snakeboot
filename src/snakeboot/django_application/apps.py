from typing import override

from django.apps import AppConfig
from django.conf import settings

from snakeboot.django_application.container_sections import complete_configuration
from snakeboot.django_application.transaction_manager import install_transaction_manager


class DjangoApplicationConfig(AppConfig):
    """Starts what snakeboot adds to Django; `django_settings` puts this app first in INSTALLED_APPS.

    When Django starts, it reads the sections of the container and, with a database, installs the transaction
    manager of `@transactional`.
    """

    name = "snakeboot.django_application"
    label = "snakeboot_django_application"
    verbose_name = "snakeboot"

    @override
    def ready(self) -> None:
        complete_configuration(settings)
        install_transaction_manager(settings)
