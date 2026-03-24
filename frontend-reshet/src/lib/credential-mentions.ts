import type { IntegrationCredential } from "@/services/credentials";

const CREDENTIAL_MENTION_RE = /@\{(?:([^{}|]*)\|)?([0-9a-fA-F-]{36})\}/g;

export function buildCredentialMentionToken(credential: Pick<IntegrationCredential, "id" | "display_name">): string {
  return `@{${credential.id}}`;
}

export function extractCredentialMentionIds(text: string): string[] {
  const ids: string[] = [];
  let match: RegExpExecArray | null;
  const regex = new RegExp(CREDENTIAL_MENTION_RE.source, "g");
  while ((match = regex.exec(text || "")) !== null) {
    ids.push(match[2]);
  }
  return ids;
}

export function canonicalizeCredentialMentions(text: string): string {
  if (!text) return text;
  return text.replace(CREDENTIAL_MENTION_RE, (_match, _currentName: string | undefined, credentialId: string) => {
    return `@{${credentialId}}`;
  });
}

export function normalizeCredentialMentionLabels(
  text: string,
  credentials: Array<Pick<IntegrationCredential, "id" | "display_name">>,
): string {
  if (!text) return text;
  const knownIds = new Set(credentials.map((credential) => credential.id));
  return text.replace(CREDENTIAL_MENTION_RE, (_match, _currentName: string | undefined, credentialId: string) => (
    knownIds.has(credentialId) ? `@{${credentialId}}` : `@{${credentialId}}`
  ));
}
