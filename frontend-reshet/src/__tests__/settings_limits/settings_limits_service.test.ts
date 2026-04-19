import { settingsLimitsService } from "@/services/settings-limits"

const getMock = jest.fn()
const patchMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
  },
}))

describe("settings limits service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("loads and updates organization and project limits", async () => {
    getMock.mockResolvedValue({})
    patchMock.mockResolvedValue({})

    await settingsLimitsService.getOrganizationLimits()
    await settingsLimitsService.updateOrganizationLimits({ monthly_token_limit: 1000 })
    await settingsLimitsService.getProjectLimits("alpha")
    await settingsLimitsService.updateProjectLimits("alpha", { monthly_token_limit: 500 })

    expect(getMock).toHaveBeenNthCalledWith(1, "/api/settings/limits/organization")
    expect(patchMock).toHaveBeenNthCalledWith(1, "/api/settings/limits/organization", { monthly_token_limit: 1000 })
    expect(getMock).toHaveBeenNthCalledWith(2, "/api/settings/limits/projects/alpha")
    expect(patchMock).toHaveBeenNthCalledWith(2, "/api/settings/limits/projects/alpha", { monthly_token_limit: 500 })
  })
})
