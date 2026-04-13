import {
  findCatalogEntry,
  matchServerToCatalog,
  pickPreferredCatalogServer,
} from "@/services/integration-catalog";

describe("integration catalog canonical MCP selection", () => {
  it("matches legacy Linear SSE rows back to the Linear catalog entry", () => {
    expect(matchServerToCatalog("https://mcp.linear.app/sse")?.slug).toBe(
      "linear"
    );
  });

  it("prefers the canonical catalog endpoint over legacy duplicates", () => {
    const entry = findCatalogEntry("linear");
    expect(entry).toBeDefined();

    const preferred = pickPreferredCatalogServer(entry!, [
      {
        id: "legacy-linear",
        server_url: "https://mcp.linear.app/sse",
        sync_status: "auth_required",
        tool_snapshot_version: 0,
        updated_at: "2026-04-12T19:13:19.590779+03:00",
      },
      {
        id: "canonical-linear",
        server_url: "https://mcp.linear.app/mcp",
        sync_status: "ready",
        tool_snapshot_version: 2,
        updated_at: "2026-04-13T18:56:15.908017+03:00",
      },
    ]);

    expect(preferred?.id).toBe("canonical-linear");
  });

  it("prefers an actively connected row when multiple rows share a provider", () => {
    const entry = findCatalogEntry("linear");
    expect(entry).toBeDefined();

    const preferred = pickPreferredCatalogServer(
      entry!,
      [
        {
          id: "older-connected",
          server_url: "https://mcp.linear.app/sse",
          sync_status: "auth_required",
          tool_snapshot_version: 0,
          updated_at: "2026-04-12T19:13:19.590779+03:00",
        },
        {
          id: "newer-unconnected",
          server_url: "https://mcp.linear.app/sse",
          sync_status: "ready",
          tool_snapshot_version: 2,
          updated_at: "2026-04-13T18:56:15.908017+03:00",
        },
      ],
      { connectedServerIds: new Set(["older-connected"]) }
    );

    expect(preferred?.id).toBe("older-connected");
  });
});
