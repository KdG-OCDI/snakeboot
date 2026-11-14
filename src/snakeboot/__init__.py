"""snakeboot: Spring Boot ergonomics for hexagonal Python applications.

What an application imports, in no framework's terms:

    snakeboot.boot            run, asgi_application, TestApplication             (extras: configuration, web)
    snakeboot.component_scan  @application_root, ComponentScan                    (no dependencies)
    snakeboot.stereotype      @component, @service, @repository, @bean            (wireup)
    snakeboot.transaction     @transactional, after_commit, TransactionManager    (no dependencies)
    snakeboot.events          ApplicationEventPublisher, @transactional_event_listener   (wireup)
    snakeboot.configuration   @configuration_properties, Section, ServerProperties   (extra: configuration)
    snakeboot.rest            @rest_controller, @route, Principal, ServerSentEvents  (wireup, pydantic)
    snakeboot.data            @entity, CrudRepository, @query, @lock              (wireup)
    snakeboot.cache           Cache, InMemoryCache                                (no dependencies)
    snakeboot.command_line    CommandLineRunner, CommandLineError                 (wireup)
    snakeboot.lifecycle       Lifecycle, ApplicationReadyEvent                    (wireup)
    snakeboot.scheduling      @scheduled                                          (extra: configuration)
    snakeboot.rabbitmq        @rabbit_listener, RabbitTemplate                    (extra: rabbitmq)
    snakeboot.oauth2          JwtBearerAuthentication                             (extra: oauth2)
    snakeboot.openapi         @openapi_definition                                 (no dependencies)
    snakeboot.testing         RecordingTransactionManager, declared_classes       (no dependencies)

What starts them and binds them to the frameworks underneath, which an application leaves to snakeboot:

    snakeboot.application      the application context: configuration, container, commands   (no framework)
    snakeboot.fastapi_web      the REST API and its event streams on FastAPI                  (extra: web)
    snakeboot.sqlalchemy_data  entities, repositories, @transactional and migrations on
                               SQLAlchemy, Alembic and PostgreSQL                             (extra: data)
    snakeboot.redis_cache      the Cache in Redis                                             (extra: cache)

The libraries imitate the basics of Spring Boot, not Spring itself: each one is a few
small classes a reader can follow, and none knows anything about the application's domain.
"""
