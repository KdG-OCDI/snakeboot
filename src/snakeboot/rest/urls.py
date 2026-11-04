"""The URL configuration of every snakeboot application: its REST API under /api/ and /health.

`django_settings` names this module as ROOT_URLCONF and the application class as the setting APPLICATION, so an
application has no urls.py of its own.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from snakeboot.rest.rest_api import url_patterns

_application = getattr(settings, "APPLICATION", None)
if not isinstance(_application, type):
    raise ImproperlyConfigured(
        "snakeboot.rest.urls needs the setting APPLICATION, the class marked with @application_root: start the "
        "application with snakeboot's run(MyApplication) or wsgi_application(MyApplication)."
    )

urlpatterns = url_patterns(_application)
