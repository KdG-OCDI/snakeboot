"""Test helpers, like spring-test and spring-security-test: tests of the whole application, doubles and mocks.

    @test_component(replaces=ClockPort)                     # @TestComponent @Primary, found in the source
    class FixedClock(ClockPort): ...

    @application_test                                       # @SpringBootTest: the one @application_root, started
    class TestInvoicing:                                    # anew for every test
        client: Autowired[RestClient]                       # @Autowired
        clock: Autowired[FixedClock]                        # the test component, by its own type
        invoices: MockComponent[InvoiceRepositoryPort]      # @MockitoBean; SpyComponent is @MockitoSpyBean

        def test_the_event_waits_while_invoicing_fails(self) -> None:
            when(self.invoices.save).then_raise(ConnectionError("down"))          # Mockito, in the port's types
            self.client.post("/api/auctions", json=..., headers=signed_in_as("carol", roles={"auctioneer"}))
            verify(self.invoices.save).called_once_with(...)

snakeboot's pytest plugin, which pytest loads by itself, starts the application of an `@application_test`.

    TransactionManagerRegistry.install(RecordingTransactionManager())    # use cases without a database

    declared = declared_classes(Path("src/myapp"), "rest_controller")    # what the source declares
    assert declared == qualified_names(urls.mounted.controllers)         # ... is what was mounted
"""

from snakeboot.testing.application_marker import (
    ApplicationTest,
    application_module_test,
    application_test,
    web_test,
)
from snakeboot.testing.component_replacements import InvalidTestComponentError, test_component
from snakeboot.testing.declared_classes import declared_classes, qualified_names
from snakeboot.testing.environment import PostgreSQLContainer, TestEnvironment
from snakeboot.testing.injection import Autowired, MockComponent, SpyComponent
from snakeboot.testing.published_events import PublishedEvents
from snakeboot.testing.recording_transaction_manager import RecordingTransactionManager
from snakeboot.testing.signed_in_tokens import signed_in_as
from snakeboot.testing.slices import ApplicationSlice, ModuleSlice, WebSlice
from snakeboot.testing.source_scan import ApplicationNotFoundError
from snakeboot.testing.stubbing import Stubbing, Verification, verify, when

__all__ = [
    "ApplicationNotFoundError",
    "ApplicationSlice",
    "ApplicationTest",
    "Autowired",
    "InvalidTestComponentError",
    "MockComponent",
    "ModuleSlice",
    "PostgreSQLContainer",
    "PublishedEvents",
    "RecordingTransactionManager",
    "SpyComponent",
    "Stubbing",
    "TestEnvironment",
    "Verification",
    "WebSlice",
    "application_module_test",
    "application_test",
    "declared_classes",
    "qualified_names",
    "signed_in_as",
    "test_component",
    "verify",
    "web_test",
    "when",
]
