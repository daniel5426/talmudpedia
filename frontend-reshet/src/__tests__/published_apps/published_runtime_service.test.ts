import { publishedRuntimeService } from "@/services/published-runtime";

describe("published runtime service transport", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
  });

  it("omits ambient browser credentials for tokenless auth requests", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ token: "token-1", token_type: "bearer", user: { id: "u1", email: "u@example.com" } }),
    });
    Object.defineProperty(globalThis, "fetch", {
      value: fetchMock,
      configurable: true,
      writable: true,
    });

    await publishedRuntimeService.login("public-1", { email: "u@example.com", password: "secret123" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/public/external/apps/public-1/auth/login");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "POST",
      credentials: "omit",
      cache: "no-store",
    });
  });

  it("uses bearer auth without cookies for runtime stream requests", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
    });
    Object.defineProperty(globalThis, "fetch", {
      value: fetchMock,
      configurable: true,
      writable: true,
    });

    await publishedRuntimeService.streamChat("public-1", { input: "hello" }, "token-abc");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/public/external/apps/public-1/chat/stream");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer token-abc",
      },
    });
  });
});
