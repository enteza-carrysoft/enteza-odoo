# -*- coding: utf-8 -*-
"""MCP protocol-revision handling.

The Model Context Protocol has been revised four times, and the 2026-07-28
revision is a breaking redesign: it deletes the ``initialize`` handshake and
protocol-level sessions, makes every request self-contained, and requires new
fields on every result.

A server that speaks only one revision is either broken for old clients or
broken for new ones. This module keeps the wire format in one place and
**negotiates per request**, because 2026-07-28 has no handshake in which to
negotiate once — the version travels with each call.

Where the version comes from, in priority order:

1. ``params._meta["io.modelcontextprotocol/protocolVersion"]`` — 2026-07-28
2. the ``MCP-Protocol-Version`` HTTP header — 2025-06-18 and later
3. ``params.protocolVersion`` on an ``initialize`` call — pre-2026-07-28
4. the legacy default

Point 4 matters: an unversioned request is an *old* client (new ones always
send a version), so the fallback is the oldest revision, not the newest. Being
generous here is what keeps the 2024-era clients that are already installed
working after an upgrade.
"""

# Newest first — order is significant for _best_common().
SUPPORTED_REVISIONS = (
    "2026-07-28",
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
LATEST_REVISION = SUPPORTED_REVISIONS[0]
# A request that names no revision predates the header, so assume the oldest.
LEGACY_REVISION = SUPPORTED_REVISIONS[-1]

# The revision that introduced the stateless core. At or above this, results
# carry resultType/cacheable metadata and the handshake is gone.
STATELESS_FROM = "2026-07-28"

META_PROTOCOL = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPS = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
META_LOG_LEVEL = "io.modelcontextprotocol/logLevel"

# JSON-RPC error codes. 2026-07-28 partitions the server-error range and
# renumbers the codes it introduced: -32000..-32019 stays implementation
# defined, -32020..-32099 belongs to the spec.
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
# Implementation-defined (ours), unchanged across revisions.
ERR_DISABLED = -32000
ERR_AUTH = -32001
ERR_FORBIDDEN = -32002
ERR_IP = -32003
ERR_RATE_LIMIT = -32004
# Spec-defined, renumbered in 2026-07-28 (old value kept for older clients).
ERR_HEADER_MISMATCH = {"2026-07-28": -32020, "_": -32001}
ERR_MISSING_CAPABILITY = {"2026-07-28": -32021, "_": -32003}
ERR_UNSUPPORTED_VERSION = {"2026-07-28": -32022, "_": -32004}

# Resource-not-found moved to Invalid Params to match JSON-RPC.
ERR_RESOURCE_NOT_FOUND = {"2026-07-28": -32602, "_": -32002}

# How long a client may cache our list results. Tool and prompt lists only
# change when an administrator edits configuration, so a minute is safe and
# saves a round trip on every single conversation turn.
LIST_TTL_MS = 60_000
CACHEABLE_METHODS = ("tools/list", "prompts/list", "resources/list",
                     "resources/read", "resources/templates/list")

SERVER_NAME = "Odoo MCP Server (Moaz Nabil · free)"


def rank(revision):
    """Position in SUPPORTED_REVISIONS; -1 when unknown.

    Dates sort lexicographically, so a plain string compare would also work —
    but only for revisions we know about. Ranking against the tuple means an
    unrecognised future date is reported as unknown instead of silently
    treated as newer than everything we implement.
    """
    try:
        return SUPPORTED_REVISIONS.index(revision)
    except ValueError:
        return -1


def is_at_least(revision, floor):
    """True when `revision` is `floor` or newer (both must be known)."""
    r, f = rank(revision), rank(floor)
    return r != -1 and f != -1 and r <= f


def err_code(table, revision):
    """Pick a revision-appropriate error code from one of the tables above."""
    return table.get(revision, table["_"])


def negotiate(body, headers):
    """Resolve the protocol revision for a single request.

    Returns ``(revision, unsupported)``. When the client asks for a revision we
    do not implement, the caller should answer with UnsupportedProtocolVersion
    rather than guessing — guessing is how you end up returning 2024-shaped
    results to a 2026 client that then fails to parse them.
    """
    params = body.get("params") or {}
    meta = params.get("_meta") or {}

    asked = (meta.get(META_PROTOCOL)
             or headers.get("MCP-Protocol-Version")
             or params.get("protocolVersion")
             or "")
    asked = (asked or "").strip()

    if not asked:
        return LEGACY_REVISION, False
    if rank(asked) == -1:
        return LATEST_REVISION, True
    return asked, False


def server_info(version):
    return {"name": SERVER_NAME, "version": version}


def capabilities(revision):
    """What we advertise. Shrinks on newer revisions as features were removed.

    Logging is deprecated from 2026-07-28 and Roots/Sampling were never
    implemented here, so there is nothing to gain by claiming them.
    """
    caps = {
        "tools": {"listChanged": False},
        "resources": {"subscribe": False, "listChanged": False},
        "prompts": {"listChanged": False},
    }
    if not is_at_least(revision, STATELESS_FROM):
        # Pre-2026 clients may look for these; they were removed from the spec.
        caps["logging"] = {}
    return caps


def decorate_result(result, revision, method, version):
    """Add the envelope fields a given revision requires.

    Older revisions must NOT receive these keys — an unknown field is
    tolerated by most clients, but the spec is explicit that resultType only
    exists from 2026-07-28, and a strict client is entitled to reject it.
    """
    if not isinstance(result, dict):
        return result
    if not is_at_least(revision, STATELESS_FROM):
        return result

    result.setdefault("resultType", "complete")
    meta = result.setdefault("_meta", {})
    meta.setdefault(META_SERVER_INFO, server_info(version))

    if method in CACHEABLE_METHODS:
        # CacheableResult: a freshness hint plus whether a shared proxy may
        # keep it. Ours is per-API-key (tool visibility depends on the key's
        # allowed models), so it is never publicly cacheable.
        result.setdefault("ttlMs", LIST_TTL_MS)
        result.setdefault("cacheScope", "private")
    return result


def discover(version):
    """``server/discover`` — mandatory from 2026-07-28.

    Clients may call it before anything else to pick a revision, and STDIO
    clients use it as a backwards-compatibility probe.
    """
    return {
        "protocolVersions": list(SUPPORTED_REVISIONS),
        "serverInfo": server_info(version),
        "capabilities": capabilities(LATEST_REVISION),
    }
