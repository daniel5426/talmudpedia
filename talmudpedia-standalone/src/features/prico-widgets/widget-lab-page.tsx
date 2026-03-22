import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

import { useLocale } from "../classic-chat/locale-context";
import { PricoWidgetBundleView, renderWidget } from "./renderer";
import { widgetLabScenarios } from "./showcase-data";

export function WidgetLabPage() {
  const { locale, isRtl } = useLocale();
  const [scenarioId, setScenarioId] = useState(widgetLabScenarios[0]?.id ?? "");
  const [showContract, setShowContract] = useState(false);

  const scenario = useMemo(
    () => widgetLabScenarios.find((item) => item.id === scenarioId) ?? widgetLabScenarios[0],
    [scenarioId],
  );

  const bundle = isRtl ? scenario.bundleHe : scenario.bundle;

  const allWidgets = useMemo(
    () => bundle.rows.flatMap((row) => row.widgets),
    [bundle],
  );

  const jsonContract = useMemo(
    () =>
      JSON.stringify(
        {
          screen_title: bundle.title,
          screen_subtitle: bundle.subtitle,
          rows: bundle.rows,
        },
        null,
        2,
      ),
    [bundle],
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 md:px-6">
        {/* Header */}
        <div className="mb-8 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-foreground">{isRtl ? "סביבת ווידג'טים" : "Widget Lab"}</h1>
              <Badge variant="outline" className="text-xs">
                {widgetLabScenarios.length} {isRtl ? "תרחישים" : "scenarios"}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {isRtl ? "בדיקת חבילות ווידג'טים, משטחים מבודדים וחוזי DSL." : "Inspect widget bundles, isolated surfaces, and DSL contracts."}
            </p>
          </div>
          <a href="/" className="text-sm font-medium text-primary hover:underline underline-offset-4">
            {isRtl ? "חזרה לצ'אט" : "Back to chat"}
          </a>
        </div>

        <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
          {/* Sidebar - Scenario selector */}
          <nav className="space-y-1.5">
            <div className="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">{isRtl ? "תרחישים" : "Scenarios"}</div>
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
                <div className="text-[0.65rem] font-medium tracking-wide uppercase opacity-70">{isRtl ? item.eyebrowHe : item.eyebrow}</div>
                <div className="text-sm font-medium">{isRtl ? item.nameHe : item.name}</div>
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
                    <CardTitle className="text-base">{isRtl ? scenario.nameHe : scenario.name}</CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">{isRtl ? scenario.descriptionHe : scenario.description}</p>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{bundle.rows.length} {isRtl ? "שורות" : "rows"}</span>
                    <Separator orientation="vertical" className="h-3" />
                    <span>{allWidgets.length} {isRtl ? "ווידג'טים" : "widgets"}</span>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <PricoWidgetBundleView bundle={bundle} />
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
                {showContract ? (isRtl ? "הסתר JSON" : "Hide JSON") : (isRtl ? "הצג JSON" : "Show JSON")}
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
                {isRtl ? "ווידג'טים מבודדים" : "Isolated Widgets"}
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
