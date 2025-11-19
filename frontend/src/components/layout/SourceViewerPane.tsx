'use client';

import React from 'react';
import { useLayoutStore } from '@/lib/store/useLayoutStore';
import { Button } from '@/components/ui/button';
import { X, Maximize2 } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';

interface SourceViewerPaneProps {
  sourceId: string;
}

export function SourceViewerPane({ sourceId }: SourceViewerPaneProps) {
  const { setActiveSource } = useLayoutStore();

  return (
    <div className="flex flex-col h-full bg-background">
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-sm">Source Viewer</h2>
          <span className="text-xs text-muted-foreground px-2 py-0.5 bg-muted rounded-full">
            {sourceId}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Maximize2 className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setActiveSource(null)} className="h-8 w-8">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <ScrollArea className="flex-1 p-6">
        <div className="max-w-3xl mx-auto prose dark:prose-invert">
          <h1 className="text-2xl font-bold mb-4">Talmud Bavli, Shabbat 21b</h1>
          <p className="text-lg leading-relaxed mb-4" dir="rtl">
            תנו רבנן: מצות חנוכה נר איש וביתו. והמהדרין - נר לכל אחד ואחד. והמהדרין מן המהדרין - בית שמאי אומרים: יום ראשון מדליק שמונה, מכאן ואילך פוחת והולך. ובית הלל אומרים: יום ראשון מדליק אחת, מכאן ואילך מוסיף והולך.
          </p>
          <p className="text-lg leading-relaxed mb-4" dir="rtl">
            אמר עולא: פליגי בה תרי אמוראי במערבא, רבי יוסי בר אבין ורבי יוסי בר זביד. חד אמר: טעמא דבית שמאי - כנגד ימים הנכנסין, וטעמא דבית הלל - כנגד ימים היוצאין. וחד אמר: טעמא דבית שמאי - כנגד פרי החג, וטעמא דבית הלל - דמעלין בקודש ואין מורידין.
          </p>
          <div className="p-4 bg-muted/50 rounded-lg my-6">
            <h3 className="font-semibold mb-2">English Translation</h3>
            <p>
              Our Rabbis taught: The mitzvah of Chanukah is one light for a man and his household. And the zealous (mehadrin) - a light for each and every one. And the zealous of the zealous - Beit Shammai says: On the first day he lights eight, from then on he decreases. And Beit Hillel says: On the first day he lights one, from then on he increases.
            </p>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
