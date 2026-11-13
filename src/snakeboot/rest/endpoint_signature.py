import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, get_args

from snakeboot.rest.principal import Principal
from snakeboot.rest.rest_controller_errors import InvalidRestControllerError
from snakeboot.rest.uploaded_file import UploadedFile

UNDECLARED: Final = inspect.Signature.empty
"""The response of an endpoint whose route names no type and whose method has no return annotation."""


@dataclass(frozen=True, slots=True)
class EndpointSignature:
    """What a web framework reads of one endpoint method: what the call fills in, and what the answer holds.

    `parameters` are the parameters after `self` that the call carries (path, query and body, or the fields of a
    form), in order, with their annotations evaluated; `principal_parameters` name the parameters of type `Principal`,
    which the framework fills with whoever the token belongs to; `upload_parameters` name those of `parameters` of
    type `UploadedFile`, which make the call a `multipart/form-data` form; `response` is the type of the body: the
    `response` of the route, else the return annotation, `None` for an empty body, and `UNDECLARED` when neither says.
    """

    parameters: tuple[inspect.Parameter, ...]
    principal_parameters: tuple[str, ...]
    response: Any
    upload_parameters: tuple[str, ...] = ()

    @classmethod
    def of(cls, owner: type, method: Callable[..., Any], response: Any = None) -> "EndpointSignature":
        """Reads the signature of `method` of `owner`; `response` overrides the return annotation.

        A method that cannot be an endpoint stops the start: an async method, a method without `self`, a method
        that takes `request` (the request belongs to the web framework), an annotation that names nothing, or an
        uploaded file that is not one plain `UploadedFile` parameter.
        """
        signature = _evaluated_signature(owner, method)
        parameters = _parameters_after_self(owner, method, signature)
        _refuse_request_parameter(owner, method, parameters)
        principals = tuple(parameter.name for parameter in parameters if parameter.annotation is Principal)
        return cls(
            parameters=tuple(parameter for parameter in parameters if parameter.name not in principals),
            principal_parameters=principals,
            response=response if response is not None else signature.return_annotation,
            upload_parameters=_upload_parameters(owner, method, parameters),
        )


def method_parameters(owner: type, method: Callable[..., Any]) -> list[inspect.Parameter]:
    """Returns the parameters of a synchronous method after `self`, with their annotations evaluated.

    Controllers and advices are synchronous singletons: an async method, or a function without `self`, stops the
    start.
    """
    return _parameters_after_self(owner, method, _evaluated_signature(owner, method))


def _evaluated_signature(owner: type, method: Callable[..., Any]) -> inspect.Signature:
    # Evaluated here, in the module of the method: a binding wraps the method in a function of its own module,
    # where a string annotation such as "WorkshopViewDTO" would name nothing.
    try:
        return inspect.signature(method, eval_str=True)
    except NameError as error:
        raise InvalidRestControllerError(
            f"An annotation of {owner.__name__}.{method.__name__} names nothing at run time: {error}. "
            "Import what the signature names outside `if TYPE_CHECKING`."
        ) from error


def _parameters_after_self(
    owner: type, method: Callable[..., Any], signature: inspect.Signature
) -> list[inspect.Parameter]:
    if inspect.iscoroutinefunction(method):
        raise InvalidRestControllerError(
            f"{owner.__name__}.{method.__name__} is async; controller endpoints are synchronous."
        )
    parameters = list(signature.parameters.values())
    if not parameters or parameters[0].name != "self":
        raise InvalidRestControllerError(
            f"{owner.__name__}.{method.__name__} must be a regular method taking `self` first."
        )
    return parameters[1:]


def _refuse_request_parameter(owner: type, method: Callable[..., Any], parameters: list[inspect.Parameter]) -> None:
    if any(parameter.name == "request" for parameter in parameters):
        raise InvalidRestControllerError(
            f"{owner.__name__}.{method.__name__} takes `request`, which belongs to the web framework. An endpoint "
            "takes what the call carries (path, query and body parameters) and, with a parameter of type Principal, "
            "who made it."
        )


def _upload_parameters(owner: type, method: Callable[..., Any], parameters: list[inspect.Parameter]) -> tuple[str, ...]:
    # One part of the form fills one parameter: a list, an optional file or a default would leave the web framework
    # to guess, and it would read such a parameter as a JSON body instead of a file.
    for parameter in parameters:
        plain = parameter.annotation is UploadedFile and parameter.default is inspect.Parameter.empty
        if not plain and _names_uploaded_file(parameter.annotation):
            raise InvalidRestControllerError(
                f"{owner.__name__}.{method.__name__} takes `{parameter}`. An endpoint takes each uploaded file as a "
                "parameter of type UploadedFile without a default, which the part of the same name fills."
            )
    return tuple(parameter.name for parameter in parameters if parameter.annotation is UploadedFile)


def _names_uploaded_file(annotation: object) -> bool:
    # `list[UploadedFile]`, `UploadedFile | None` and `Annotated[UploadedFile, ...]` name it in their arguments.
    return annotation is UploadedFile or any(_names_uploaded_file(argument) for argument in get_args(annotation))
