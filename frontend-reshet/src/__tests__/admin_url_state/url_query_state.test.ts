import { buildQueryStringWithValue, coerceQueryEnum } from "@/lib/urlQueryState"

describe("urlQueryState", () => {
  it("coerces invalid enum values to the fallback", () => {
    expect(coerceQueryEnum("roles", ["assignments", "roles", "workloads"] as const, "assignments")).toBe("roles")
    expect(coerceQueryEnum("invalid", ["assignments", "roles", "workloads"] as const, "assignments")).toBe("assignments")
    expect(coerceQueryEnum(null, ["assignments", "roles", "workloads"] as const, "assignments")).toBe("assignments")
  })

  it("sets and clears query params while preserving unrelated values", () => {
    expect(buildQueryStringWithValue("foo=1", "tab", "roles", "assignments")).toBe("foo=1&tab=roles")
    expect(buildQueryStringWithValue("foo=1&tab=roles", "tab", "assignments", "assignments")).toBe("foo=1")
  })
})
