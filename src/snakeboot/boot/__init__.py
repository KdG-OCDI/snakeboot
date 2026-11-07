"""How an application starts, whatever runs underneath, like Spring Boot's `SpringApplication.run`.

    # myapp/__main__.py and manage.py              # myapp/asgi.py, for uvicorn
    run(MyApplication)                             application = asgi_application(MyApplication)
                                                   # myapp/wsgi.py, for gunicorn
                                                   application = wsgi_application(MyApplication)

These are the only names an application's entry points import. `run` runs a command: one of the application's
`CommandLineRunner`s, or one of the framework's own (`migrate`, `runserver`). Today the application starts on Django
(`snakeboot.django_application`); another framework would change this module, not the applications
(extras: snakeboot[configuration,django]).
"""

from snakeboot.django_application.entry_points import asgi_application, run, wsgi_application

__all__ = ["asgi_application", "run", "wsgi_application"]
