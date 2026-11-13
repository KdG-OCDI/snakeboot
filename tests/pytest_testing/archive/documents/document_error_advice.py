from snakeboot.rest import error_answer, exception_handler, rest_controller_advice
from tests.pytest_testing.archive.documents.read_document import DocumentNotFoundError


@rest_controller_advice
class DocumentErrorAdvice:
    @exception_handler(DocumentNotFoundError, status=404)
    def answer_not_found(self, error: Exception) -> dict[str, str]:
        return error_answer(error)
