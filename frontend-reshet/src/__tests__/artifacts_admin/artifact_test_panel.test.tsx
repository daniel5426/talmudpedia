import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import { ArtifactTestPanel } from "@/components/admin/artifacts/ArtifactTestPanel"

const createTestRun = jest.fn()
const getRun = jest.fn()
const getRunEvents = jest.fn()

jest.mock("@/services/artifacts", () => ({
  artifactsService: {
    createTestRun: (...args: unknown[]) => createTestRun(...args),
    getRun: (...args: unknown[]) => getRun(...args),
    getRunEvents: (...args: unknown[]) => getRunEvents(...args),
  },
}))

jest.mock("@/components/ui/code-editor", () => ({
  CodeEditor: ({ value, onChange, className }: { value: string; onChange: (value: string) => void; className?: string }) => (
    <div className={className}>
      <div data-testid="mock-code-editor-value">{value}</div>
      <button
        type="button"
        onClick={() => {
          onChange('{"message":"fresh"}')
          document.getElementById("artifact-test-panel-execute")?.click()
        }}
      >
        apply-and-run
      </button>
    </div>
  ),
}))

describe("ArtifactTestPanel", () => {
  beforeEach(() => {
    createTestRun.mockReset()
    getRun.mockReset()
    getRunEvents.mockReset()
    createTestRun.mockResolvedValue({ run_id: "run-1", status: "queued" })
    getRun.mockResolvedValue({
      id: "run-1",
      artifact_id: "artifact-1",
      revision_id: "revision-1",
      domain: "test",
      status: "completed",
      queue_class: "artifact_test",
      result_payload: { ok: true },
      error_payload: null,
      stdout_excerpt: null,
      stderr_excerpt: null,
      duration_ms: 5,
      runtime_metadata: {},
      created_at: "2026-03-25T00:00:00Z",
      started_at: "2026-03-25T00:00:01Z",
      finished_at: "2026-03-25T00:00:02Z",
    })
    getRunEvents.mockResolvedValue({ run_id: "run-1", event_count: 0, events: [] })
  })

  it("uses the latest edited input when run is triggered in the same interaction", async () => {
    render(
      <ArtifactTestPanel
        tenantSlug="tenant"
        artifactId="artifact-1"
        sourceFiles={[{ path: "main.py", content: "async def execute(inputs, config, context):\n    return inputs\n" }]}
        entryModulePath="main.py"
        language="python"
        kind="tool_impl"
        runtimeTarget="cloudflare_workers"
        capabilities={{
          network_access: false,
          allowed_hosts: [],
          secret_refs: [],
          storage_access: [],
          side_effects: [],
        }}
        configSchema={{ type: "object", properties: {} }}
        toolContract={{
          input_schema: {
            type: "object",
            required: ["message"],
            properties: {
              message: { type: "string" },
            },
          },
          output_schema: {},
          side_effects: [],
          execution_mode: "interactive",
          tool_ui: {},
        }}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Expand test runtime" }))
    fireEvent.click(await screen.findByRole("button", { name: "apply-and-run" }))

    await waitFor(() => {
      expect(createTestRun).toHaveBeenCalledWith(
        expect.objectContaining({
          input_data: { message: "fresh" },
        }),
        "tenant",
      )
    })
  })
})
