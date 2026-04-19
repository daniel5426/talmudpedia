import { settingsProfileService } from "@/services/settings-profile"

const getMock = jest.fn()
const patchMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
  },
}))

describe("settings profile service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("loads and updates the personal profile", async () => {
    getMock.mockResolvedValue({ id: "u1" })
    patchMock.mockResolvedValue({ id: "u1", full_name: "New Name" })

    await settingsProfileService.getProfile()
    await settingsProfileService.updateProfile({ full_name: "New Name", avatar: null })

    expect(getMock).toHaveBeenCalledWith("/api/settings/profile")
    expect(patchMock).toHaveBeenCalledWith("/api/settings/profile", {
      full_name: "New Name",
      avatar: null,
    })
  })
})
