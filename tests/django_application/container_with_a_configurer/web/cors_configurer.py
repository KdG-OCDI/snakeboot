from snakeboot.django_application import DjangoConfigurer


class CorsConfigurer(DjangoConfigurer):
    """An app from outside the project with its middleware, as django-cors-headers needs them."""

    installed_apps = ("corsheaders",)
    middleware = ("corsheaders.middleware.CorsMiddleware",)
