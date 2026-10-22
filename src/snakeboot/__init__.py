"""snakeboot: Spring Boot ergonomics for hexagonal Python applications.

    snakeboot.transaction     @transactional, after_commit, TransactionManager    (no dependencies)
    snakeboot.component_scan  @application_root, ComponentScan                    (no dependencies)
    snakeboot.events          ApplicationEventPublisher, @transactional_event_listener   (wireup)
    snakeboot.rest            @rest_controller, @route, @rest_controller_advice   (extra: ninja)
    snakeboot.django          DjangoAtomicTransactionManager                      (extra: django)
    snakeboot.testing         RecordingTransactionManager, declared_classes       (no dependencies)

The libraries imitate the basics of Spring Boot, not Spring itself: each one is a few
small classes a reader can follow, and none knows anything about the application's domain.
"""
