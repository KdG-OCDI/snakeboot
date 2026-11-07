from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("scheduling")
class SchedulingProperties(Section):
    """The optional section `[scheduling]`: whether this process runs the `@scheduled` methods.

    Without the section they run, as in Spring Boot. A web process whose scheduled work runs in a process of its own
    (`run_lifecycle`) turns them off, usually through the environment of its container:

        [scheduling]
        auto_startup = false          # or SCHEDULING__AUTO_STARTUP=false
    """

    auto_startup: bool
