"""Django integration of the container and the configuration (extras: `snakeboot[configuration,django]`).

    # settings.py, at the bottom
    COMPONENT_SCAN = ComponentScan(base_packages=("myservice_core",))
    configure_django(__name__, package="myservice", component_scan=COMPONENT_SCAN)

`configure_django` sets Django's settings from application.toml (`[django]`, and `[database]` and `[cache]` when
they are there) and the container from the component scan. When Django starts, this app reads the sections declared
in the modules of the container, so settings.py lists no section and no wireup setting.
"""

from snakeboot.django_application.configure_django import APPLICATION, configure_django

__all__ = ["APPLICATION", "configure_django"]
