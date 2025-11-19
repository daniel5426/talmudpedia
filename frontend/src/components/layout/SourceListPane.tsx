'use client';

import React from 'react';
import { useLayoutStore } from '@/lib/store/useLayoutStore';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { BookOpen, X } from 'lucide-react';

const DUMMY_SOURCES = [
  { id: 'shabbat-21b', title: 'Shabbat 21b', subtitle: 'Talmud Bavli' },
  { id: 'shulchan-aruch-670', title: 'Shulchan Aruch 670', subtitle: 'Orach Chayim' },
  { id: 'rambam-chanukah', title: 'Hilchot Chanukah 4:1', subtitle: 'Mishneh Torah' },
];

export function SourceListPane() {
  const { setActiveSource, toggleSourceList } = useLayoutStore();

  return (
    <div className="flex flex-col h-full bg-muted/30">
      <div className="flex items-center justify-between p-4 border-b">
        <h2 className="font-semibold text-sm">Sources</h2>
        <Button variant="ghost" size="icon" onClick={toggleSourceList} className="h-8 w-8">
          <X className="h-4 w-4" />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-2">
          {DUMMY_SOURCES.map((source) => (
            <div
              key={source.id}
              className="p-3 rounded-lg border bg-card hover:bg-accent/50 cursor-pointer transition-colors"
              onClick={() => setActiveSource(source.id)}
            >
              <div className="flex items-center gap-2 mb-1">
                <BookOpen className="h-4 w-4 text-primary" />
                <span className="font-medium text-sm">{source.title}</span>
              </div>
              <p className="text-xs text-muted-foreground pl-6">{source.subtitle}</p>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
