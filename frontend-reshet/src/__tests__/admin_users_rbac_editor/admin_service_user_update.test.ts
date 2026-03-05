import { adminService } from "@/services/admin"

const patchMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    patch: (...args: unknown[]) => patchMock(...args),
  },
}))

describe("admin user update api", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("updates only profile fields", async () => {
    patchMock.mockResolvedValue(undefined)

    await adminService.updateUser("user-1", { full_name: "Name" })

    expect(patchMock).toHaveBeenCalledWith("/admin/users/user-1", { full_name: "Name" })
  })
})
