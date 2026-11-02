from pydantic import BaseModel, ConfigDict


class Section(BaseModel):
    """A table of application.toml as a class: a frozen Pydantic model that refuses unknown keys.

    Every section and every table nested in it extends `Section`, so a typo in a key stops the start and a value
    cannot change while the application runs. Give no field a default: every value is written in application.toml
    or in a profile, where everyone can read it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
