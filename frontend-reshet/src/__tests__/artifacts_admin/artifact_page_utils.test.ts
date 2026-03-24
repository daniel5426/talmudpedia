import {
  buildArtifactPayload,
  formDataFromArtifact,
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
          content: `from artifact_runtime_sdk import outbound_fetch\n\nasync def execute(inputs, config, context):\n    return await outbound_fetch("https://api.openai.com/v1/responses", credential="${buildCredentialMentionToken(credential)}")\n`,
        },
      ],
    };

    const payload = buildArtifactPayload(formData);

    expect(payload.runtime.source_files[0].content).toContain(credential.id);
    expect("credential_bindings" in payload).toBe(false);
  });

  it("hydrates form data from artifact responses without credential bindings", () => {
    const artifact: Artifact = {
      id: "artifact-1",
      display_name: "Mention Artifact",
      description: "",
      kind: "tool_impl",
      owner_type: "tenant",
      type: "draft",
      version: "draft",
      config_schema: {},
      runtime: {
        source_files: [{ path: "main.py", content: "def execute(inputs, config, context):\n    return {'ok': True}\n" }],
        entry_module_path: "main.py",
        python_dependencies: [],
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
});
