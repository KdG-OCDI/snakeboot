"""Sample asgi entry point: it starts the server when imported, so the scan must never import it."""

raise RuntimeError("asgi.py was imported by the component scan")
