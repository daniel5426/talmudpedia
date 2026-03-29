import type { UIBlocksBundle } from "@agents24/ui-blocks-contract";
import { useMemo, useState } from "react";

import { UIBlocksBundleView } from "@/components/ui-blocks";
import { ALL_THEMES } from "@/components/ui-blocks/lib/widget-theme";
import { cn } from "@/lib/utils";

import { useLocale } from "../classic-chat/locale-context";
import type { PricoWidgetBundle } from "./contract";
import { widgetLabScenarios } from "./showcase-data";

type LabScenario = (typeof widgetLabScenarios)[number];

function toUIBlocksBundle(bundle: PricoWidgetBundle): UIBlocksBundle {
  return {
    title: bundle.title,
    subtitle: bundle.subtitle,
    rows: bundle.rows.map((row) => ({
      blocks: row.widgets,
    })),
  };
}

function scenarioLabel(scenario: LabScenario, isRtl: boolean) {
  return {
    name: isRtl ? scenario.nameHe : scenario.name,
  };
}

function bundleForScenario(scenario: LabScenario, isRtl: boolean): PricoWidgetBundle {
  return isRtl ? scenario.bundleHe : scenario.bundle;
}

export function WidgetLabPage() {
  const { isRtl } = useLocale();
  const [scenarioId, setScenarioId] = useState(widgetLabScenarios[0]?.id ?? "");

  const scenario = useMemo(
    () => widgetLabScenarios.find((item) => item.id === scenarioId) ?? widgetLabScenarios[0],
    [scenarioId],
  );

  const scenarioBundle = useMemo(
    () => toUIBlocksBundle(bundleForScenario(scenario, isRtl)),
    [scenario, isRtl],
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-6xl px-6 py-10">
        {/* Scenario selector */}
        <div className="flex gap-2 overflow-x-auto pb-8">
          {widgetLabScenarios.map((item) => {
            const copy = scenarioLabel(item, isRtl);
            const selected = item.id === scenarioId;
            return (
              <button
                key={item.id}
                onClick={() => setScenarioId(item.id)}
                className={cn(
                  "shrink-0 rounded-full border px-4 py-1.5 text-sm transition",
                  selected
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300",
                )}
              >
                {copy.name}
              </button>
            );
          })}
        </div>

        {/* All 5 themes */}
        <div className="space-y-12">
          {ALL_THEMES.map((theme) => (
            <section key={theme.id}>
              <div className="mb-4 flex items-center gap-3">
                <h2 className="text-sm font-medium text-slate-900">{theme.name}</h2>
                <div className="h-px flex-1 bg-slate-200" />
              </div>
              <div
                className={cn(
                  "rounded-2xl p-6",
                  theme.id === "midnight" ? "bg-slate-900" : "bg-white border border-slate-100",
                )}
              >
                <UIBlocksBundleView bundle={scenarioBundle} theme={theme} />
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
