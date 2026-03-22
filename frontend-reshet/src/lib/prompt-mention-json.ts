const PROMPT_TOKEN_RE = /\[\[prompt:([0-9a-fA-F-]{36})\]\]/g;

export interface JsonStringRange {
  from: number;
  to: number;
}

export interface JsonPromptTokenRange extends JsonStringRange {
  promptId: string;
  name: string;
}

interface ParsedJsonString {
  decoded: string;
  endQuote: number;
  contentFrom: number;
  contentTo: number;
}

function skipWhitespace(text: string, index: number): number {
  let cursor = index;
  while (cursor < text.length && /\s/.test(text[cursor])) {
    cursor += 1;
  }
  return cursor;
}

function parseJsonString(text: string, startQuote: number): ParsedJsonString | null {
  if (text[startQuote] !== '"') {
    return null;
  }
  let decoded = "";
  let cursor = startQuote + 1;
  while (cursor < text.length) {
    const char = text[cursor];
    if (char === "\\") {
      const next = text[cursor + 1];
      if (next === undefined) return null;
      decoded += char + next;
      cursor += 2;
      continue;
    }
    if (char === '"') {
      return {
        decoded,
        endQuote: cursor,
        contentFrom: startQuote + 1,
        contentTo: cursor,
      };
    }
    decoded += char;
    cursor += 1;
  }
  return null;
}

export function findDescriptionValueRanges(text: string): JsonStringRange[] {
  const ranges: JsonStringRange[] = [];
  let cursor = 0;

  while (cursor < text.length) {
    if (text[cursor] !== '"') {
      cursor += 1;
      continue;
    }

    const key = parseJsonString(text, cursor);
    if (!key) {
      cursor += 1;
      continue;
    }

    let next = skipWhitespace(text, key.endQuote + 1);
    if (text[next] !== ":") {
      cursor = key.endQuote + 1;
      continue;
    }

    next = skipWhitespace(text, next + 1);
    if (key.decoded === "description" && text[next] === '"') {
      const value = parseJsonString(text, next);
      if (value) {
        ranges.push({ from: value.contentFrom, to: value.contentTo });
        cursor = value.endQuote + 1;
        continue;
      }
    }

    cursor = key.endQuote + 1;
  }

  return ranges;
}

export function findPromptTokensInDescriptionValues(
  text: string,
  nameMap: Record<string, string>
): JsonPromptTokenRange[] {
  const tokens: JsonPromptTokenRange[] = [];

  for (const range of findDescriptionValueRanges(text)) {
    const rawValue = text.slice(range.from, range.to);
    let match: RegExpExecArray | null;
    const re = new RegExp(PROMPT_TOKEN_RE.source, "g");
    while ((match = re.exec(rawValue)) !== null) {
      const promptId = match[1];
      tokens.push({
        promptId,
        name: nameMap[promptId] ?? "Unknown Prompt",
        from: range.from + match.index,
        to: range.from + match.index + match[0].length,
      });
    }
  }

  return tokens;
}

export interface JsonPromptQueryMatch {
  query: string;
  replaceFrom: number;
  replaceTo: number;
}

export function getJsonPromptQueryAtPosition(
  text: string,
  position: number
): JsonPromptQueryMatch | null {
  const range = findDescriptionValueRanges(text).find(
    (candidate) => position >= candidate.from && position <= candidate.to
  );
  if (!range) {
    return null;
  }

  const beforeCursor = text.slice(range.from, position);
  const match = beforeCursor.match(/@([^\s@]*)$/);
  if (!match || match.index === undefined) {
    return null;
  }

  return {
    query: match[1],
    replaceFrom: range.from + match.index,
    replaceTo: position,
  };
}

export function replaceJsonTextRange(
  text: string,
  from: number,
  to: number,
  replacement: string
): string {
  return text.slice(0, from) + replacement + text.slice(to);
}

export function escapeForJsonStringContent(value: string): string {
  return JSON.stringify(value).slice(1, -1);
}
