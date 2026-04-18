import { resolveDirectBackendStreamBaseUrl } from "@/services/published-apps";

describe("coding agent stream URL resolution", () => {
  it("keeps the browser loopback hostname for local direct SSE", () => {
    const resolved = resolveDirectBackendStreamBaseUrl(
      "http://localhost:8026",
      "http://localhost:8026",
      "127.0.0.1",
    );

    expect(resolved).toBe("http://127.0.0.1:8026/");
  });

  it("preserves non-loopback backend hosts", () => {
    const resolved = resolveDirectBackendStreamBaseUrl(
      "https://api.example.com",
      "https://api.example.com",
      "127.0.0.1",
    );

    expect(resolved).toBe("https://api.example.com/");
  });
});
