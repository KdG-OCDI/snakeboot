"""Django settings for snakeboot's own tests: one small app with one table, an in-memory database."""

SECRET_KEY = "snakeboot-tests-only"
INSTALLED_APPS = ["tests.django_integration.notes"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
