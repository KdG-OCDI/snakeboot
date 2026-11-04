from snakeboot.django_application import DjangoConfigurer


class SecurityHeadersConfigurer(DjangoConfigurer):
    """A configurer of the service itself, next to its application class."""

    middleware = ("django.middleware.security.SecurityMiddleware",)
