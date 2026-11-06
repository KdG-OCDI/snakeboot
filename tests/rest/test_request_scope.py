"""A controller is resolved from wireup's request scope under WSGI and under ASGI alike."""

import asyncio

import pytest
import wireup
from wireup import injectable

from snakeboot.rest import controller_endpoint_factory
from snakeboot.rest.controller_endpoint_factory import resolve_from_wireup_request_scope


@injectable
class Greeter:
    """A singleton to resolve."""


def test_under_wsgi_the_synchronous_request_scope_resolves_it(monkeypatch: pytest.MonkeyPatch) -> None:
    container = wireup.create_sync_container(injectables=[Greeter])
    with container.enter_scope() as scope:
        monkeypatch.setattr(controller_endpoint_factory, "get_request_container", lambda: scope)

        assert isinstance(resolve_from_wireup_request_scope(Greeter), Greeter)


def test_under_asgi_the_asynchronous_request_scope_resolves_it_without_a_coroutine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve_in_an_asgi_request() -> object:
        container = wireup.create_async_container(injectables=[Greeter])
        async with container.enter_scope() as scope:
            monkeypatch.setattr(controller_endpoint_factory, "get_request_container", lambda: scope)
            # The endpoint runs in a worker thread, as Django runs a synchronous view under ASGI.
            return await asyncio.to_thread(resolve_from_wireup_request_scope, Greeter)

    assert isinstance(asyncio.run(resolve_in_an_asgi_request()), Greeter)
