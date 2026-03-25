import { fireEvent, render, screen } from "@testing-library/react"

import { ArtifactListView } from "@/components/admin/artifacts/ArtifactListView"
import type { Artifact } from "@/services/artifacts"

jest.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSeparator: () => <div />,
  DropdownMenuItem: ({ children, onClick, disabled, className }: any) => (
    <button type="button" onClick={onClick} disabled={disabled} className={className}>
      {children}
    </button>
  ),
}))

const baseArtifact: Artifact = {
  id: "artifact-1",
  display_name: "Email Validator",
  description: "Validates emails",
  kind: "tool_impl",
  owner_type: "tenant",
  type: "draft",
  version: "draft",
  config_schema: {},
  runtime: {
    language: "javascript",
    source_files: [],
    entry_module_path: "main.js",
    dependencies: [],
    runtime_target: "cloudflare_workers",
  },
  capabilities: {
    network_access: false,
    allowed_hosts: [],
    secret_refs: [],
    storage_access: [],
    side_effects: [],
  },
  tool_contract: {
    input_schema: {},
    output_schema: {},
    side_effects: [],
    execution_mode: "sync",
    tool_ui: {},
  },
  tags: [],
  updated_at: "2026-03-25T00:00:00Z",
}

describe("ArtifactListView", () => {
  it("opens the artifact editor when the display name is clicked", () => {
    const onEditArtifact = jest.fn()
    render(
      <ArtifactListView
        artifacts={[baseArtifact]}
        publishingId={null}
        onEditArtifact={onEditArtifact}
        onDeleteArtifact={jest.fn()}
        onPublishArtifact={jest.fn()}
        onDuplicateArtifact={jest.fn()}
      />,
    )

    fireEvent.click(screen.getByText("Email Validator"))
    expect(onEditArtifact).toHaveBeenCalledWith(baseArtifact)
  })

  it("routes actions through the dropdown menu handlers", () => {
    const onDuplicateArtifact = jest.fn()
    const onPublishArtifact = jest.fn()
    const onDeleteArtifact = jest.fn()
    render(
      <ArtifactListView
        artifacts={[baseArtifact]}
        publishingId={null}
        onEditArtifact={jest.fn()}
        onDeleteArtifact={onDeleteArtifact}
        onPublishArtifact={onPublishArtifact}
        onDuplicateArtifact={onDuplicateArtifact}
      />,
    )

    fireEvent.click(screen.getByText("Duplicate"))
    fireEvent.click(screen.getByText("Publish"))
    fireEvent.click(screen.getByText("Delete"))

    expect(onDuplicateArtifact).toHaveBeenCalledWith(baseArtifact)
    expect(onPublishArtifact).toHaveBeenCalledWith(baseArtifact)
    expect(onDeleteArtifact).toHaveBeenCalledWith(baseArtifact)
  })
})
