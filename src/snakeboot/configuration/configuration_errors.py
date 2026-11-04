class InvalidConfigurationPropertiesError(TypeError):
    """Raised at start-up when a class cannot be bound to a section of the configuration.

    A model that does not extend `Section` or changes its `model_config`, a default in code, an unmarked
    section or two models claiming the same section. Like an invalid `@ConfigurationProperties` class in
    Spring, it stops the application from starting.
    """


class ConfigurationFileNotFoundError(FileNotFoundError):
    """Raised at start-up when `application.toml`, or the file of the active profile, is not in the package."""
