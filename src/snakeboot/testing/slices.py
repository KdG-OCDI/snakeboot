from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebSlice:
    """The REST layer of an application, like Spring Boot's `@WebMvcTest`.

    It holds the modules that declare a `@rest_controller`, a `@rest_controller_advice` or the API's
    `BearerAuthentication`, and the modules that declare a section; every other module of the application is left
    out. What a controller needs from there, a use case most of all, a test gives as a `MockComponent`.
    """


@dataclass(frozen=True, slots=True)
class ModuleSlice:
    """Bounded contexts of an application on their own, like Spring Modulith's `@ApplicationModuleTest`.

    It holds the modules of `packages`, the modules right in the application's package (its root, its tokens: what
    every context shares) and the modules that declare a section; the other contexts are left out. What the contexts
    need from another one, a test gives as a `MockComponent`, as Spring Modulith's `STANDALONE` mode asks.
    """

    packages: tuple[str, ...]

    def holds(self, module_name: str) -> bool:
        """Tells whether `module_name` is one of `packages` or lies under one of them."""
        return any(module_name == package or module_name.startswith(f"{package}.") for package in self.packages)


type ApplicationSlice = WebSlice | ModuleSlice
"""The part of an application a test starts: `WebSlice` or `ModuleSlice`."""
