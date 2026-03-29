"use client"

import { useState } from "react"
import { Artifact } from "@/services"
import { ArtifactDependencyTab } from "@/components/admin/artifacts/ArtifactDependencyTab"
import { ArtifactKind, ArtifactLanguage } from "@/services/artifacts"
import { ArtifactFormData, RUNTIME_TARGET_OPTIONS } from "@/components/admin/artifacts/artifactEditorState"
import { contractEditorTitle } from "@/components/admin/artifacts/artifactPageUtils"
import { Button } from "@/components/ui/button"
import { JsonEditor } from "@/components/ui/json-editor"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { PromptMentionJsonEditor } from "@/components/shared/PromptMentionJsonEditor"
import { Loader2 } from "lucide-react"

interface ArtifactConfigPanelProps {
  formData: ArtifactFormData;
  tenantSlug?: string;
  selectedArtifact: Artifact | null;
  viewMode: "list" | "create" | "edit";
  convertTargetKind: ArtifactKind;
  converting: boolean;
  currentContractValue: string;
  onUpdateFormData: (field: keyof ArtifactFormData, value: string | ArtifactKind | ArtifactLanguage | ArtifactFormData["source_files"]) => void;
  onUpdateCurrentContract: (value: string) => void;
  onConvertTargetKindChange: (value: ArtifactKind) => void;
  onConvertKind: () => void;
  onPromptMentionClick: (promptId: string, tokenRange: { from: number; to: number }) => void;
  onCopyConfig: () => void;
  onPasteConfig: () => void;
  configClipboardStatus?: string | null;
}

export function ArtifactConfigPanel({
  formData,
  tenantSlug,
  selectedArtifact,
  viewMode,
  convertTargetKind,
  converting,
  currentContractValue,
  onUpdateFormData,
  onUpdateCurrentContract,
  onConvertTargetKindChange,
  onConvertKind,
  onPromptMentionClick,
  onCopyConfig,
  onPasteConfig,
  configClipboardStatus,
}: ArtifactConfigPanelProps) {
  const [activeTab, setActiveTab] = useState("general")

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto bg-background [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-border">
      <div className="mx-auto w-full max-w-5xl px-6 py-12 md:px-12">
        <div className="mb-12 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-xl font-medium tracking-tight">Configuration Profile</h2>
            <p className="mt-1 text-sm text-muted-foreground/80">Properties, runtime targets, and boundary definitions.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {configClipboardStatus ? (
              <span className="text-xs text-muted-foreground">{configClipboardStatus}</span>
            ) : null}
            <Button type="button" variant="outline" size="sm" onClick={onCopyConfig}>
              Copy config
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onPasteConfig}>
              Paste config
            </Button>
          </div>
        </div>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-8">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="dependencies">Dependencies</TabsTrigger>
            <TabsTrigger value="contract">Contract</TabsTrigger>
            <TabsTrigger value="capabilities">Capabilities</TabsTrigger>
            <TabsTrigger value="schema">Schema</TabsTrigger>
          </TabsList>

          <TabsContent value="general" className="m-0">
            <div className="grid grid-cols-1 gap-x-5 gap-y-12 lg:grid-cols-2">
              <div className="space-y-6">
                <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  <span className="mr-3 text-primary">01</span> Identity
                </h3>

                <div className="group relative">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Display Name</Label>
                  <input
                    value={formData.display_name}
                    onChange={(e) => onUpdateFormData("display_name", e.target.value)}
                    className="w-full rounded-md border border-border/40 bg-transparent px-3 py-2 text-sm text-foreground outline-none shadow-none transition-colors hover:border-border focus:border-primary focus:ring-0"
                    placeholder="e.g. Data Extractor Agent"
                  />
                </div>

                <div className="group relative">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Artifact Type</Label>
                  <div className="flex h-[38px] w-full items-center rounded-md border border-border/40 bg-transparent px-3">
                    <span className="text-sm">{formData.kind === "agent_node" ? "Agent Node" : formData.kind === "rag_operator" ? "RAG Operator" : "Tool Implementation"} · {formData.language === "javascript" ? "JS/TS" : "Python"}</span>
                  </div>
                </div>

                <div className="group relative pt-2">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Description</Label>
                  <Textarea
                    value={formData.description}
                    onChange={(e) => onUpdateFormData("description", e.target.value)}
                    rows={3}
                    placeholder="Briefly describe the artifact's purpose..."
                    className="w-full resize-none rounded-md border border-border/40 bg-transparent p-3 text-sm text-foreground outline-none shadow-none transition-colors hover:border-border focus:border-primary focus:ring-0"
                  />
                </div>
              </div>

              <div className="space-y-6">
                <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  <span className="mr-3 text-primary">02</span> Execution
                </h3>

                <div className="group relative">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Entry Module Path</Label>
                  <input
                    value={formData.entry_module_path}
                    onChange={(e) => onUpdateFormData("entry_module_path", e.target.value)}
                    className="w-full rounded-md border border-border/40 bg-transparent px-3 py-2 font-mono text-sm text-foreground outline-none shadow-none transition-colors hover:border-border focus:border-primary focus:ring-0"
                  />
                </div>

                <div className="group relative">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Target Environment</Label>
                  <Select value={formData.runtime_target} onValueChange={(value) => onUpdateFormData("runtime_target", value)}>
                    <SelectTrigger className="h-[38px] w-full rounded-md border border-border/40 bg-transparent px-3 text-sm shadow-none focus:ring-0 focus:ring-offset-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="rounded-md border-border">
                      {RUNTIME_TARGET_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value} className="text-sm">{option.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {viewMode === "edit" && selectedArtifact?.type === "draft" && selectedArtifact.owner_type === "tenant" && (
                  <div className="mt-8 pt-4">
                    <Label className="mb-2 block text-xs font-medium text-destructive/80 transition-colors group-hover:text-destructive">Danger Zone</Label>
                    <div className="flex items-center gap-3 rounded-md border border-border/40 p-1">
                      <Select value={convertTargetKind} onValueChange={(value) => onConvertTargetKindChange(value as ArtifactKind)}>
                        <SelectTrigger className="h-[34px] w-full border-0 bg-transparent text-sm shadow-none focus:ring-0 focus:ring-offset-0">
                          <SelectValue placeholder="Convert kind to..." />
                        </SelectTrigger>
                        <SelectContent className="rounded-md border-border">
                          {(["agent_node", "rag_operator", "tool_impl"] as ArtifactKind[]).filter((option) => option !== formData.kind).map((option) => (
                            <SelectItem key={option} value={option} className="text-sm">
                              {option === "agent_node" ? "Agent Node" : option === "rag_operator" ? "RAG Operator" : "Tool Implementation"}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button variant="ghost" className="h-[34px] shrink-0 rounded-md px-2 text-xs font-medium text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={onConvertKind} disabled={converting}>
                        {converting ? <Loader2 className="h-3 w-3 animate-spin" /> : "Convert"}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="dependencies" className="m-0">
            <ArtifactDependencyTab
              language={formData.language}
              sourceFiles={formData.source_files}
              dependencies={formData.dependencies}
              tenantSlug={tenantSlug}
              onChangeDependencies={(value) => onUpdateFormData("dependencies", value)}
            />
          </TabsContent>

          <TabsContent value="contract" className="m-0">
            <div>
              <div className="mb-3 flex items-end justify-between">
                <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  <span className="mr-3 text-primary">03</span> {contractEditorTitle(formData.kind)}
                </h3>
                <span className="text-[10px] text-muted-foreground">JSON</span>
              </div>
              <div className="h-[480px] w-full rounded-md border border-border/40 bg-muted/5 p-1 transition-colors hover:border-border/80 focus-within:border-primary">
                {formData.kind === "tool_impl" ? (
                  <PromptMentionJsonEditor
                    value={currentContractValue}
                    onChange={onUpdateCurrentContract}
                    height="100%"
                    className="h-full border-0 bg-transparent"
                    surface="artifact.tool_contract.description"
                    onMentionClick={(promptId, tokenRange) => onPromptMentionClick(promptId, tokenRange)}
                  />
                ) : (
                  <JsonEditor value={currentContractValue} onChange={onUpdateCurrentContract} height="100%" className="h-full border-0 bg-transparent" />
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="capabilities" className="m-0">
            <div>
              <div className="mb-3 flex items-end justify-between">
                <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  <span className="mr-3 text-primary">04</span> Runtime Capabilities
                </h3>
                <span className="text-[10px] text-muted-foreground">JSON</span>
              </div>
              <div className="h-[480px] w-full rounded-md border border-border/40 bg-muted/5 p-1 transition-colors hover:border-border/80 focus-within:border-primary">
                <JsonEditor value={formData.capabilities} onChange={(value) => onUpdateFormData("capabilities", value)} height="100%" className="h-full border-0 bg-transparent" />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="schema" className="m-0">
            <div>
              <div className="mb-3 flex items-end justify-between">
                <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  <span className="mr-3 text-primary">05</span> Configuration Schema
                </h3>
                <span className="text-[10px] text-muted-foreground">JSON SCHEMA</span>
              </div>
              <div className="h-[480px] w-full rounded-md border border-border/40 bg-muted/5 p-1 transition-colors hover:border-border/80 focus-within:border-primary">
                <JsonEditor value={formData.config_schema} onChange={(value) => onUpdateFormData("config_schema", value)} height="100%" className="h-full border-0 bg-transparent" />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
