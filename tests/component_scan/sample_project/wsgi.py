"""Sample wsgi entry point: it starts the server when imported, so the scan must never import it."""

raise RuntimeError("wsgi.py was imported by the component scan")
