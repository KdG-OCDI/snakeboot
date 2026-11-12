"""Binds `snakeboot.testing` to pytest: an `@application_test` starts its application and gets what it asks for.

pytest loads `snakeboot.pytest_testing.pytest_plugin` by itself, through the entry point `pytest11` of snakeboot; an
application's tests import `snakeboot.testing` and never this package. It is the one part of snakeboot that knows
pytest, as `snakeboot.fastapi_web` is the one that knows FastAPI, so another test runner means another binding.
"""

__all__: list[str] = []
