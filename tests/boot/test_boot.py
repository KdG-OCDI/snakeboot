"""`snakeboot.boot` is where an application's entry points import from, whichever framework runs underneath."""

from snakeboot import boot
from snakeboot.django_application import entry_points


def test_an_application_starts_on_django_today() -> None:
    assert (boot.run, boot.wsgi_application, boot.asgi_application) == (
        entry_points.run,
        entry_points.wsgi_application,
        entry_points.asgi_application,
    )


def test_it_offers_nothing_but_the_entry_points() -> None:
    assert sorted(boot.__all__) == ["asgi_application", "run", "wsgi_application"]
