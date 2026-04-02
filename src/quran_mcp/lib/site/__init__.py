"""Public browser/docs HTTP surface wrapped around the inner FastMCP app.

This package owns the non-MCP HTTP routes exposed by the server, such as the
landing page, documentation shell, health endpoint, markdown downloads, and
asset-backed public files. The public route contract is declared in the
manifest; the installer composes that surface around FastMCP's inner transport
app without changing how MCP protocol traffic is handled.
"""

from .surface import mount_public_routes

__all__ = ["mount_public_routes"]
