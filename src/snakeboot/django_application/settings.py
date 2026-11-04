"""The Django settings of every snakeboot application.

DJANGO_SETTINGS_MODULE names this module, and SNAKEBOOT_APPLICATION the class marked with `@application_root`;
`run` and `wsgi_application` set both. The settings are built from that class and its application.toml, so an
application has no settings.py of its own, and nothing can change them after snakeboot.
"""

from snakeboot.django_application.django_settings import django_settings
from snakeboot.django_application.entry_points import application_named_in_environment

globals().update(django_settings(application_named_in_environment()))
