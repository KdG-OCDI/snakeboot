from pydantic import BaseModel, ConfigDict


class Section(BaseModel):
    """The base class of every configuration model: a table of application.toml as a class.

    A section marked with `@configuration_properties` extends `Section`, and so does every table nested in it: it
    refuses unknown keys, so a typo in a key stops the start, and it is frozen, so a value cannot change while the
    application runs. `load_configuration` refuses a model that does not extend `Section` or changes its
    `model_config`.

    A separate rule of `load_configuration`, not of this class: no field has a default. Every value is written in
    application.toml, a profile or the environment, where everyone can read it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
