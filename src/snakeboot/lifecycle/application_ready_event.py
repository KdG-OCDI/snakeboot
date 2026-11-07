from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApplicationReadyEvent:
    """Published once every `Lifecycle` component has started, like Spring Boot's `ApplicationReadyEvent`.

    The place for work that must happen once per start, such as registering with another service:

        @application_event_listener
        class RegisterOnStartup:
            @event_listener(ApplicationReadyEvent)
            def register(self, event: ApplicationReadyEvent) -> None: ...

    A listener that raises stops the start-up, as in Spring Boot.
    """
