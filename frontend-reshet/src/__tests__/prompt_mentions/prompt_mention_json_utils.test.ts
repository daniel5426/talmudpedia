import {
  escapeForJsonStringContent,
  findDescriptionValueRanges,
  findPromptTokensInDescriptionValues,
  getJsonPromptQueryAtPosition,
  replaceJsonTextRange,
} from "@/lib/prompt-mention-json"

describe("prompt mention json utilities", () => {
  const jsonText = JSON.stringify(
    {
      type: "object",
      properties: {
        category: {
          type: "string",
          description: "Classify with [[prompt:11111111-1111-1111-1111-111111111111]]",
        },
        label: {
          type: "string",
          title: "Ignored",
        },
      },
      description: "Parent @tone",
    },
    null,
    2
  )

  it("finds only description string ranges", () => {
    const ranges = findDescriptionValueRanges(jsonText)
    expect(ranges.length).toBe(2)
    expect(jsonText.slice(ranges[0].from, ranges[0].to)).toContain("[[prompt:")
    expect(jsonText.slice(ranges[1].from, ranges[1].to)).toContain("@tone")
  })

  it("finds prompt tokens only inside description values", () => {
    const tokens = findPromptTokensInDescriptionValues(jsonText, {
      "11111111-1111-1111-1111-111111111111": "Classifier Prompt",
    })

    expect(tokens).toEqual([
      expect.objectContaining({
        promptId: "11111111-1111-1111-1111-111111111111",
        name: "Classifier Prompt",
      }),
    ])
  })

  it("detects @ queries only inside description values", () => {
    const queryPosition = jsonText.indexOf("@tone") + "@tone".length
    expect(getJsonPromptQueryAtPosition(jsonText, queryPosition)).toEqual({
      query: "tone",
      replaceFrom: jsonText.indexOf("@tone"),
      replaceTo: queryPosition,
    })

    const outsidePosition = jsonText.indexOf('"title": "Ignored"') + 5
    expect(getJsonPromptQueryAtPosition(jsonText, outsidePosition)).toBeNull()
  })

  it("replaces one json token range with escaped raw content", () => {
    const [token] = findPromptTokensInDescriptionValues(jsonText, {})
    const filled = replaceJsonTextRange(
      jsonText,
      token.from,
      token.to,
      escapeForJsonStringContent('Line 1\nLine "2"')
    )

    expect(filled).toContain('Line 1\\nLine \\"2\\"')
    expect(filled).not.toContain("[[prompt:")
  })
})
