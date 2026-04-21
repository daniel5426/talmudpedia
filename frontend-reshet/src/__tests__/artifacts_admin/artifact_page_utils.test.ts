import {
  buildArtifactPayload,
  buildArtifactConfigClipboardText,
  formDataFromArtifact,
  getArtifactLanguageWarningPaths,
  parseArtifactConfigClipboardText,
  parseToolContract,
  serializeArtifactFormData,
} from "@/components/admin/artifacts/artifactPageUtils";
import { createFormDataForKind } from "@/components/admin/artifacts/artifactEditorState";
import { buildCredentialMentionToken, extractCredentialMentionIds, normalizeCredentialMentionLabels } from "@/lib/credential-mentions";
import type { Artifact, IntegrationCredential } from "@/services";

describe("artifactPageUtils and credential mentions", () => {
  const credential: IntegrationCredential = {
    id: "11111111-1111-1111-1111-111111111111",
    category: "llm_provider",
    provider_key: "openai",
    provider_variant: null,
    display_name: "My OpenAI Key",
    credential_keys: ["api_key"],
    is_enabled: true,
    is_default: true,
    created_at: "2026-03-24T00:00:00Z",
    updated_at: "2026-03-24T00:00:00Z",
  };

  it("builds a valid credential mention token and extracts its id", () => {
    const token = buildCredentialMentionToken(credential);

    expect(token).toBe("@{11111111-1111-1111-1111-111111111111}");
    expect(extractCredentialMentionIds(`credential="${token}"`)).toEqual([credential.id]);
  });

  it("normalizes legacy named tokens to the safe id-only form", () => {
    const value = 'credential="@{Old Name|11111111-1111-1111-1111-111111111111}"';

    expect(normalizeCredentialMentionLabels(value, [credential])).toBe(
      'credential="@{11111111-1111-1111-1111-111111111111}"',
    );
  });

  it("builds artifact payloads without artifact-side credential bindings", () => {
    const formData = {
      ...createFormDataForKind("tool_impl"),
      display_name: "Mention Tool",
      source_files: [
        {
          path: "main.py",
          content: `from openai import OpenAI\n\nasync def execute(inputs, config, context):\n    client = OpenAI(api_key="${buildCredentialMentionToken(credential)}")\n    return {"ok": bool(client)}\n`,
        },
      ],
    };

    const payload = buildArtifactPayload(formData);

    expect(payload.runtime.source_files[0].content).toContain(credential.id);
    expect("credential_bindings" in payload).toBe(false);
  });

  it("propagates artifact draft_key into save payloads", () => {
    const formData = {
      ...createFormDataForKind("tool_impl"),
      display_name: "Draft Linked Tool",
    };

    const payload = buildArtifactPayload(formData, "draft-link-1");

    expect(payload.draft_key).toBe("draft-link-1");
  });

  it("hydrates form data from artifact responses without credential bindings", () => {
    const artifact: Artifact = {
      id: "artifact-1",
      display_name: "Mention Artifact",
      description: "",
      kind: "tool_impl",
      owner_type: "organization",
      type: "draft",
      version: "draft",
      config_schema: {},
      runtime: {
        language: "python",
        source_files: [{ path: "main.py", content: "def execute(inputs, config, context):\n    return {'ok': True}\n" }],
        entry_module_path: "main.py",
        dependencies: [],
        runtime_target: "cloudflare_workers",
      },
      capabilities: {
        network_access: true,
        allowed_hosts: [],
        secret_refs: [],
        storage_access: [],
        side_effects: [],
      },
      tool_contract: {
        input_schema: { type: "object" },
        output_schema: { type: "object" },
        side_effects: [],
        execution_mode: "interactive",
        tool_ui: {},
      },
      updated_at: "2026-03-24T00:00:00Z",
      tags: [],
    };

    const formData = formDataFromArtifact(artifact);
    expect(Object.prototype.hasOwnProperty.call(formData, "credential_bindings")).toBe(false);
  });

  it("rejects wrapped tool contracts", () => {
    expect(() =>
      parseToolContract(JSON.stringify({
        tool_contract: {
          input_schema: { type: "object" },
          output_schema: { type: "object" },
        },
      })),
    ).toThrow("Tool contract must be the inner contract object");
  });

  it("warns only for opposite-language code files and ignores neutral files", () => {
    expect(
      getArtifactLanguageWarningPaths("javascript", [
        { path: "main.js" },
        { path: "helper.py" },
        { path: "notes.txt" },
        { path: "data.json" },
      ]),
    ).toEqual(["helper.py"]);

    expect(
      getArtifactLanguageWarningPaths("python", [
        { path: "main.py" },
        { path: "helper.ts" },
        { path: "notes.txt" },
        { path: "data.json" },
      ]),
    ).toEqual(["helper.ts"]);
  });

  it("normalizes dependency and json formatting in form signatures", () => {
    const base = createFormDataForKind("tool_impl");
    const compact = {
      ...base,
      dependencies: "requests,httpx",
      tool_contract: '{"output_schema":{"type":"object"},"input_schema":{"type":"object"},"tool_ui":{},"side_effects":[],"execution_mode":"interactive"}',
    };
    const pretty = {
      ...base,
      dependencies: "requests, httpx",
      tool_contract: JSON.stringify({
        input_schema: { type: "object" },
        output_schema: { type: "object" },
        side_effects: [],
        execution_mode: "interactive",
        tool_ui: {},
      }, null, 2),
    };

    expect(serializeArtifactFormData(compact)).toBe(serializeArtifactFormData(pretty));
  });

  it("round-trips copied artifact configuration payloads", () => {
    const formData = {
      ...createFormDataForKind("tool_impl", "javascript"),
      display_name: "Shared Config",
      description: "Moves across accounts",
      entry_module_path: "main.js",
      dependencies: "zod, openai",
    };

    const text = buildArtifactConfigClipboardText(formData);
    const parsed = parseArtifactConfigClipboardText(text, {
      kind: "tool_impl",
      language: "javascript",
      source_files: formData.source_files,
    });

    expect(parsed).toMatchObject({
      display_name: "Shared Config",
      description: "Moves across accounts",
      entry_module_path: "main.js",
      dependencies: "zod, openai",
      runtime_target: "cloudflare_workers",
    });
  });

  it("rejects copied configuration when the artifact kind does not match", () => {
    const formData = createFormDataForKind("tool_impl", "javascript");
    const text = buildArtifactConfigClipboardText(formData);

    expect(() =>
      parseArtifactConfigClipboardText(text, {
        kind: "agent_node",
        language: "javascript",
        source_files: [{ path: "main.js", content: "" }],
      }),
    ).toThrow("Copied configuration kind does not match this artifact");
  });

  it("rejects copied configuration when the entry module path is missing locally", () => {
    const formData = createFormDataForKind("tool_impl", "javascript");
    const text = buildArtifactConfigClipboardText({
      ...formData,
      entry_module_path: "src/main.js",
    });

    expect(() =>
      parseArtifactConfigClipboardText(text, {
        kind: "tool_impl",
        language: "javascript",
        source_files: [{ path: "main.js", content: "" }],
      }),
    ).toThrow("Copied entry module path does not exist in this artifact's files");
  });
});
