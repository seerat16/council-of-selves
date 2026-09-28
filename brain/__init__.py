"""Council of Selves — brain package.

Only the server process (and the modules it imports: ingest, recall, records)
touches Cognee. The CLI and Plan B runner are pure HTTP clients over the brain
server, so importing `brain.cli` or `brain.council_local` does NOT import cognee.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
