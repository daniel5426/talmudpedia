import { render, screen, waitFor } from "@testing-library/react"

import FilesPage from "@/app/admin/files/page"
import { DirectionProvider } from "@/components/direction-provider"

const listMock = jest.fn()

jest.mock("@/services", () => ({
  fileSpacesService: {
    list: (...args: unknown[]) => listMock(...args),
    create: jest.fn(),
  },
}))

describe("files page", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("renders file spaces returned by the service", async () => {
    listMock.mockResolvedValue({
      items: [
        {
          id: "space-1",
          organization_id: "organization-1",
          project_id: "project-1",
          name: "Research Workspace",
          description: "City crawl outputs",
          status: "active",
          file_count: 12,
          total_bytes: 15360,
          created_at: "2026-04-16T00:00:00Z",
          updated_at: "2026-04-16T00:00:00Z",
        },
      ],
    })

    render(
      <DirectionProvider>
        <FilesPage />
      </DirectionProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText("Research Workspace")).toBeInTheDocument()
    })
    expect(screen.getByText("City crawl outputs")).toBeInTheDocument()
    expect(screen.getByText("12 files")).toBeInTheDocument()
    expect(screen.getByText("15 KB")).toBeInTheDocument()
  })
})
