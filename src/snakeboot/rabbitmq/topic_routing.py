"""How a topic exchange routes: a routing key against the binding key of a queue or a stream."""


def routes(binding_key: str, routing_key: str) -> bool:
    """Tells whether a topic exchange routes `routing_key` to a queue bound with `binding_key`: `*` stands for one
    word of the routing key, `#` for any number."""
    return _words_match(binding_key.split("."), routing_key.split("."))


def _words_match(pattern: list[str], words: list[str]) -> bool:
    if not pattern:
        return not words
    head, rest = pattern[0], pattern[1:]
    if head == "#":
        return any(_words_match(rest, words[skipped:]) for skipped in range(len(words) + 1))
    return bool(words) and head in {"*", words[0]} and _words_match(rest, words[1:])
