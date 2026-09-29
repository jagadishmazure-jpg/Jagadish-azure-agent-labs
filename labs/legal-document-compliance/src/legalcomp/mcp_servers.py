"""Three MCP tool servers (in-process offline) with small, read-only tool surfaces:

* docintel  - `analyze_layout` (Azure AI Document Intelligence prebuilt-layout stand-in)
* clauses   - `extract_clauses`
* tables    - `extract_tables`

Calls go through labcore's McpGateway, which checks a mocked managed-identity token for the server's
audience and app role before each call."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from labcore.identity import MockManagedIdentityCredential
from labcore.mcp_gateway import McpGateway, McpServerRef
from legalcomp import extract

docintel = MCPServer("docintel", instructions="Document layout stand-in. Read-only.")
clauses = MCPServer("clauses", instructions="Clause segmentation. Read-only.")
tables = MCPServer("tables", instructions="Table extraction. Read-only.")


@docintel.tool()
def analyze_layout(doc_id: str) -> dict:
    """Return pages, lines (with OCR confidence) and tables for a document id."""
    try:
        return extract.analyze_layout(doc_id)
    except FileNotFoundError as exc:
        raise ToolError(f"unknown document {doc_id}") from exc


@clauses.tool()
def extract_clauses(doc_id: str, accepted_pages: list[int]) -> dict:
    """Split accepted pages into numbered clauses."""
    layout = extract.analyze_layout(doc_id)
    return {"clauses": extract.segment_clauses(doc_id, layout["pages"], accepted_pages)}


@tables.tool()
def extract_tables(doc_id: str, accepted_pages: list[int]) -> dict:
    """Normalise every table; tables that cannot be trusted are returned under needs_review."""
    layout = extract.analyze_layout(doc_id)
    return extract.normalise_tables(layout["pages"], accepted_pages)


AUDIENCES = {
    "docintel": "api://labs-docintel",
    "clauses": "api://labs-clauses",
    "tables": "api://labs-tables",
}
DENY = ("*delete*", "*sign*", "*execute*", "*send*")


def gateway(credential: MockManagedIdentityCredential | None = None) -> McpGateway:
    cred = credential or MockManagedIdentityCredential(
        client_id="mi-legal-compliance",
        role_grants={
            AUDIENCES["docintel"]: {"Documents.Read"},
            AUDIENCES["clauses"]: {"Clauses.Read"},
            AUDIENCES["tables"]: {"Tables.Read"},
        },
    )
    gw = McpGateway(cred, deny=DENY)
    gw.register(
        McpServerRef("docintel", docintel, AUDIENCES["docintel"], {"analyze_layout": "Documents.Read"})
    )
    gw.register(McpServerRef("clauses", clauses, AUDIENCES["clauses"], {"extract_clauses": "Clauses.Read"}))
    gw.register(McpServerRef("tables", tables, AUDIENCES["tables"], {"extract_tables": "Tables.Read"}))
    return gw
