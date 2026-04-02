# Setup Guide

## Two paths

### Path 1: Integrate with quran-mcp

#### Pattern A: Compose another MCP server

If you are building another MCP server and want it to expose the canonical
Quran tool surface plus your own tools, use FastMCP composition. This is the
real "build on top" pattern.

```python
from fastmcp import Context, FastMCP
from fastmcp.server import create_proxy

mcp = FastMCP("quran-mcp-auth")
mcp.mount(create_proxy("https://mcp.quran.ai"))


@mcp.tool
def list_bookmarks(user_id: str) -> list[dict]:
    """Return the user's saved ayah bookmarks."""
    ...


@mcp.tool
async def resume_reading(user_id: str, ctx: Context) -> dict:
    """
    Resume the user's reading journey from saved state.
    """
    last_ayah = load_last_reading_position(user_id)
    packet = await mcp.call_tool(
        "fetch_quran",
        {"ayahs": last_ayah},
    )
    return {
        "last_ayah": last_ayah,
        "quran": packet.structured_content,
    }


@mcp.tool
async def study_last_reading(user_id: str, ctx: Context) -> dict:
    """
    Build a personalized study packet from the user's current reading state.
    """
    state = load_reading_state(user_id)
    quran = await mcp.call_tool(
        "fetch_quran",
        {"ayahs": f"{state.current_ayah},{state.next_ayah}"},
    )
    tafsir = await mcp.call_tool(
        "fetch_tafsir",
        {
            "ayahs": state.current_ayah,
            "editions": state.preferred_tafsir,
        },
    )
    return {
        "current_ayah": state.current_ayah,
        "preferred_tafsir": state.preferred_tafsir,
        "quran": quran.structured_content,
        "tafsir": tafsir.structured_content,
    }
```

If you mount the public server without a namespace, the upstream tool surface
stays intact:

- `fetch_quran`
- `fetch_tafsir`
- `search_quran`
- `list_editions`

This is the right pattern for something like `quran-mcp-auth`: one MCP server
that can do everything `quran-mcp` normally does, while also adding
authenticated personal-study tools such as bookmarks, resume-reading, and
user-specific study workflows.

Keep the personal layer explicit. Let the mounted canonical surface stay
visible, and add your own auth-owned tools around it. Only introduce a
namespace if you actually need collision isolation.

`quran-mcp` itself is public at `https://mcp.quran.ai`, so you do not need
auth or an `/sse` suffix for this upstream.

If you are composing against some *other* upstream that does require auth, use
an authenticated client and proxy that client instead:

```python
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.server import create_proxy

upstream = Client(
    "https://secured-upstream.example.com/mcp",
    auth=BearerAuth(token="your-access-token"),
)

mcp.mount(create_proxy(upstream))
```

If that secured upstream collides with tools you already define locally, then
add a namespace deliberately. Do not namespace by default just because you can.

#### Pattern B: Use quran-mcp as a client inside a normal app

If your app just needs canonical Quran tools for its own workflows, treat
`quran-mcp` as an upstream MCP service and call it as a client. This is the
pattern used by `quran-mcp-admin`.

```python
import re

from fastmcp import Client

GROUNDING_NONCE_RE = re.compile(r"<grounding_nonce>(.*?)</grounding_nonce>")


async def fetch_study_context():
    async with Client("https://mcp.quran.ai") as client:
        grounding = await client.call_tool_mcp("fetch_grounding_rules", {})
        text = grounding.content[0].text
        nonce = GROUNDING_NONCE_RE.search(text).group(1)

        quran = await client.call_tool_mcp(
            "fetch_quran",
            {
                "ayahs": "2:255-256",
                "editions": "ar-simple-clean",
                "grounding_nonce": nonce,
            },
        )
        tafsir = await client.call_tool_mcp(
            "fetch_tafsir",
            {
                "ayahs": "2:255",
                "editions": "en-ibn-kathir",
                "grounding_nonce": nonce,
            },
        )
        return {
            "quran": quran.structuredContent,
            "tafsir": tafsir.structuredContent,
        }
```

This is for web apps, workers, dashboards, or internal tools that need Quran
retrieval/search results but do **not** need to expose a new MCP server. No
database, no GoodMem, and no data loading are required in your app just to
consume the canonical tool surface.

### Path 2: Collaborator setup (full local stack)

For contributors who want to modify the server itself, add new tools, or work with local data.

**Setup:**

```bash
git clone https://github.com/quran/quran-mcp.git
cd quran-mcp
cp .env.example .env                    # edit: set QURAN_MCP_DB_PASSWORD
docker compose up -d                    # start the stack
```

> **Note on data:** The database content dumps and migration SQL files are temporarily
> excluded from the repository while we work out a distribution approach that adds
> value to contributors while respecting the rights of content copyright holders.
> The server will start but tools will not return data until the database is
> populated separately.
>
> **In the meantime**, if you want to build on top of quran-mcp today, use
> **Path 1** above — mount the public server at `https://mcp.quran.ai` via
> proxy and add your own tools around it. No local data needed.

**Prerequisites:**
- Docker and Docker Compose

**Verify:**

```bash
curl http://localhost:8088/.health      # should return healthy
```
