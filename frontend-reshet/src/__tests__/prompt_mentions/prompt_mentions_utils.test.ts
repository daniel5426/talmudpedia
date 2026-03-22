import {
  extractPromptIds,
  fillMentionInValue,
  parseToSegments,
  serializeSegments,
} from "@/lib/prompt-mentions"

describe("prompt mention string utilities", () => {
  it("parses and serializes persisted prompt tokens", () => {
    const value = "Intro [[prompt:11111111-1111-1111-1111-111111111111]] outro"
    const segments = parseToSegments(value, {
      "11111111-1111-1111-1111-111111111111": "Tone Prompt",
    })

    expect(segments).toEqual([
      { type: "text", text: "Intro " },
      {
        type: "mention",
        promptId: "11111111-1111-1111-1111-111111111111",
        name: "Tone Prompt",
      },
      { type: "text", text: " outro" },
    ])
    expect(serializeSegments(segments)).toBe(value)
  })

  it("extracts prompt ids in order", () => {
    expect(
      extractPromptIds(
        "[[prompt:11111111-1111-1111-1111-111111111111]] [[prompt:22222222-2222-2222-2222-222222222222]]"
      )
    ).toEqual([
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
    ])
  })

  it("fills only the targeted mention occurrence", () => {
    const value =
      "[[prompt:11111111-1111-1111-1111-111111111111]] then [[prompt:22222222-2222-2222-2222-222222222222]]"

    expect(fillMentionInValue(value, 2, "expanded raw text")).toBe(
      "[[prompt:11111111-1111-1111-1111-111111111111]] then expanded raw text"
    )
  })
})
