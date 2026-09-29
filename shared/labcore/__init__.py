"""labcore: the reusable layers every lab is built on (config switch, tracing, Foundry client,
MAF middleware, MCP gateway with managed identity, workflow helpers, eval gate).

Nothing here talks to Azure. Each Azure-facing piece has an offline stand-in and a stub adapter
selected by `LAB_MODE`."""

__all__ = ["__version__"]
__version__ = "0.1.0"
