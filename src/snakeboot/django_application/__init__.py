"""Django integration of the application: its settings, its container and its start (extras `configuration`, `django`).

    # myapp/myapp_application.py
    @application_root(base_packages=("myapp_core",))
    class MyApplication: ...

    # manage.py and myapp/__main__.py            # myapp/wsgi.py, for gunicorn
    run(MyApplication)                            application = wsgi_application(MyApplication)
                                                  # myapp/asgi.py, for uvicorn
                                                  application = asgi_application(MyApplication)

Like Spring Boot, the application writes no settings: snakeboot builds them from the application class and its
application.toml (`django_settings`). When Django starts, this app reads the sections declared in the modules of the
container and, with a database, installs the transaction manager of `@transactional`. A `DjangoConfigurer` in the
scan adds Django apps and middleware from outside the project.
"""

from snakeboot.django_application.django_configurer import DjangoConfigurer
from snakeboot.django_application.django_settings import APPLICATION_SETTING, django_settings
from snakeboot.django_application.entry_points import (
    APPLICATION_VARIABLE,
    SETTINGS_MODULE,
    asgi_application,
    run,
    wsgi_application,
)
from snakeboot.django_application.installed_apps import APPLICATION

__all__ = [
    "APPLICATION",
    "APPLICATION_SETTING",
    "APPLICATION_VARIABLE",
    "SETTINGS_MODULE",
    "DjangoConfigurer",
    "asgi_application",
    "django_settings",
    "run",
    "wsgi_application",
]
