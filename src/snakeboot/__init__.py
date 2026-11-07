"""snakeboot: Spring Boot ergonomics for hexagonal Python applications.

What an application imports, in no framework's terms:

    snakeboot.boot            run, asgi_application, wsgi_application            (extras: configuration, django)
    snakeboot.component_scan  @application_root, ComponentScan                    (no dependencies)
    snakeboot.transaction     @transactional, after_commit, TransactionManager    (no dependencies)
    snakeboot.events          ApplicationEventPublisher, @transactional_event_listener   (wireup)
    snakeboot.configuration   @configuration_properties, Section, ServerProperties   (extra: configuration)
    snakeboot.rest            @rest_controller, @route, Principal, BearerAuthentication  (wireup)
    snakeboot.command_line    CommandLineRunner, CommandLineError                 (wireup)
    snakeboot.lifecycle       Lifecycle, ApplicationReadyEvent                    (wireup)
    snakeboot.scheduling      @scheduled                                          (extras: configuration, django)
    snakeboot.rabbitmq        @rabbit_listener, RabbitTemplate                    (extra: rabbitmq)
    snakeboot.oauth2          JwtBearerAuthentication                             (extra: oauth2)
    snakeboot.openapi         @openapi_definition                                 (no dependencies)
    snakeboot.testing         RecordingTransactionManager, declared_classes       (no dependencies)

What binds them to the frameworks underneath, which an application leaves to snakeboot:

    snakeboot.django_application  settings, container, entry points and commands on Django
    snakeboot.django_ninja        the REST API on Django Ninja
    snakeboot.django              @transactional on Django's transaction.atomic

The libraries imitate the basics of Spring Boot, not Spring itself: each one is a few
small classes a reader can follow, and none knows anything about the application's domain.
"""
