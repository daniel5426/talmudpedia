/**
 * Prompt mention utilities.
 *
 * Persisted format:  [[prompt:<UUID>]]
 * Display format:    @PromptName (rendered as a blue pill in the editor)
 *
 * These utilities convert between the two representations and support
 * the rich-text PromptMentionInput component.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROMPT_TOKEN_RE = /\[\[prompt:([0-9a-fA-F-]{36})\]\]/g;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A segment of text that is either plain text or a prompt mention. */
export type MentionSegment =
  | { type: "text"; text: string }
  | { type: "mention"; promptId: string; name: string };

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

/**
 * Extract all prompt IDs referenced in a persisted string.
 */
export function extractPromptIds(text: string): string[] {
  if (!text) return [];
  const ids: string[] = [];
  let match: RegExpExecArray | null;
  const re = new RegExp(PROMPT_TOKEN_RE.source, "g");
  while ((match = re.exec(text)) !== null) {
    ids.push(match[1]);
  }
  return ids;
}

/**
 * Parse a persisted string into segments of plain text and mentions.
 *
 * The caller must provide a lookup map of prompt id -> name so that mention
 * segments can carry the display name.
 */
export function parseToSegments(
  text: string,
  nameMap: Record<string, string>
): MentionSegment[] {
  if (!text) return [];
  const segments: MentionSegment[] = [];
  let cursor = 0;
  const re = new RegExp(PROMPT_TOKEN_RE.source, "g");
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > cursor) {
      segments.push({ type: "text", text: text.slice(cursor, match.index) });
    }
    const promptId = match[1];
    segments.push({
      type: "mention",
      promptId,
      name: nameMap[promptId] ?? "Unknown Prompt",
    });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    segments.push({ type: "text", text: text.slice(cursor) });
  }
  return segments;
}

// ---------------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------------

/**
 * Serialize segments back into a persisted string with [[prompt:UUID]] tokens.
 */
export function serializeSegments(segments: MentionSegment[]): string {
  return segments
    .map((seg) =>
      seg.type === "mention" ? `[[prompt:${seg.promptId}]]` : seg.text
    )
    .join("");
}

/**
 * Replace a single mention occurrence (by index in the segments array) with
 * the given plain text, returning a new segments array.
 */
export function fillMention(
  segments: MentionSegment[],
  mentionIndex: number,
  fillText: string
): MentionSegment[] {
  return segments.map((seg, idx) => {
    if (idx === mentionIndex) {
      return { type: "text", text: fillText };
    }
    return seg;
  });
}

/**
 * Check whether a persisted string contains any prompt tokens.
 */
export function hasPromptTokens(text: string): boolean {
  if (!text) return false;
  return new RegExp(PROMPT_TOKEN_RE.source).test(text);
}
