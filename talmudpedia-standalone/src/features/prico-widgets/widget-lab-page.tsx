import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

import { PricoWidgetBundleView, renderWidget } from "./renderer";
import { widgetLabScenarios } from "./showcase-data";

export function WidgetLabPage() {
  const [scenarioId, setScenarioId] = useState(widgetLabScenarios[0]?.id ?? "");
  const [showContract, setShowContract] = useState(false);

  const scenario = useMemo(
    () => widgetLabScenarios.find((item) => item.id === scenarioId) ?? widgetLabScenarios[0],
    [scenarioId],
  );

  const allWidgets = useMemo(
    () => scenario.bundle.rows.flatMap((row) => row.widgets),
    [scenario],
  );

  const jsonContract = useMemo(
    () =>
      JSON.stringify(
        {
          screen_title: scenario.bundle.title,
          screen_subtitle: scenario.bundle.subtitle,
          rows: scenario.bundle.rows,
        },
        null,
        2,
      ),
    [scenario],
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 md:px-6">
        {/* Header */}
        <div className="mb-8 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-foreground">Widget Lab</h1>
              <Badge variant="outline" className="text-xs">
                {widgetLabScenarios.length} scenarios
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Inspect widget bundles, isolated surfaces, and DSL contracts.
            </p>
          </div>
          <a href="/" className="text-sm font-medium text-primary hover:underline underline-offset-4">
            Back to chat
          </a>
        </div>

        <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
          {/* Sidebar - Scenario selector */}
          <nav className="space-y-1.5">
            <div className="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">Scenarios</div>
            {widgetLabScenarios.map((item) => (
              <button
                key={item.id}
                onClick={() => setScenarioId(item.id)}
                className={cn(
                  "w-full rounded-sm border px-3 py-2.5 text-left transition-colors",
                  item.id === scenarioId
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-card-foreground hover:bg-muted",
                )}
              >
                <div className="text-[0.65rem] font-medium tracking-wide uppercase opacity-70">{item.eyebrow}</div>
                <div className="text-sm font-medium">{item.name}</div>
              </button>
            ))}
          </nav>

          {/* Main content */}
          <div className="space-y-6">
            {/* Full bundle preview */}
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base">{scenario.name}</CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">{scenario.description}</p>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{scenario.bundle.rows.length} rows</span>
                    <Separator orientation="vertical" className="h-3" />
                    <span>{allWidgets.length} widgets</span>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <PricoWidgetBundleView bundle={scenario.bundle} />
              </CardContent>
            </Card>

            {/* Coverage + Contract */}
            <div className="flex items-center gap-3">
              <div className="flex flex-wrap gap-1.5">
                {Array.from(new Set(allWidgets.map((w) => w.kind))).map((kind) => (
                  <Badge key={kind} variant="secondary" className="text-xs font-normal">
                    {kind}
                  </Badge>
                ))}
              </div>
              <div className="flex-1" />
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowContract((value) => !value)}
              >
                {showContract ? "Hide JSON" : "Show JSON"}
              </Button>
            </div>

            {showContract ? (
              <pre className="overflow-x-auto rounded-sm border border-border bg-primary p-4 text-xs leading-5 text-primary-foreground">
                {jsonContract}
              </pre>
            ) : null}

            {/* Isolated widgets */}
            <div>
              <Separator className="mb-6" />
              <div className="mb-4 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Isolated Widgets
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                {allWidgets.map((widget) => (
                  <div key={widget.id} className="col-span-1">
                    {renderWidget({ ...widget, span: 12 })}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
