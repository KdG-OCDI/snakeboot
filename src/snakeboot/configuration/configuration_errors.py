class InvalidConfigurationPropertiesError(TypeError):
    """Raised at start-up when a class cannot be bound to a section of the configuration.

    A default in code, a model that ignores unknown keys, an unmarked section or two models claiming
    the same section: each would let a value come from somewhere else than application.toml, the active
    profile or the environment. Like an invalid `@ConfigurationProperties` class in Spring, it stops the
    application from starting.
    """


class ConfigurationFileNotFoundError(FileNotFoundError):
    """Raised at start-up when `application.toml`, or the file of the active profile, is not in the package."""
