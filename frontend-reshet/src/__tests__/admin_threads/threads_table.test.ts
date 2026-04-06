import { buildThreadTableRows } from "@/components/admin/threads-table"

describe("buildThreadTableRows", () => {
  it("keeps child threads directly under their root rows", () => {
    const rows = buildThreadTableRows([
      {
        id: "root-1",
        title: "Root thread",
        updated_at: "2026-04-06T10:00:00Z",
        lineage: {
          root_thread_id: "root-1",
          parent_thread_id: null,
          depth: 0,
          is_root: true,
        },
      },
      {
        id: "child-1",
        title: "Child thread",
        updated_at: "2026-04-06T10:01:00Z",
        lineage: {
          root_thread_id: "root-1",
          parent_thread_id: "root-1",
          depth: 1,
          is_root: false,
        },
      },
      {
        id: "grandchild-1",
        title: "Grandchild thread",
        updated_at: "2026-04-06T10:02:00Z",
        lineage: {
          root_thread_id: "root-1",
          parent_thread_id: "child-1",
          depth: 2,
          is_root: false,
        },
      },
      {
        id: "root-2",
        title: "Second root",
        updated_at: "2026-04-06T09:59:00Z",
        lineage: {
          root_thread_id: "root-2",
          parent_thread_id: null,
          depth: 0,
          is_root: true,
        },
      },
    ] as any)

    expect(rows.map((row) => `${row.id}:${row._treeDepth}`)).toEqual([
      "root-1:0",
      "child-1:1",
      "grandchild-1:2",
      "root-2:0",
    ])
  })
})
