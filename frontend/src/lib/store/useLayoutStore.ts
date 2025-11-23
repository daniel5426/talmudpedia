import { create } from 'zustand';

export interface Source {
  id: string;
  score: number;
  metadata: {
    index_title: string;
    ref: string;
    text: string;
    version_title?: string;
    [key: string]: string | number | undefined;
  };
}

interface LayoutState {
  isSourceListOpen: boolean;
  activeSource: string | null;
  activeChatId: string | null;
  sourceViewerWidth: number;
  sourceList: Source[];
  toggleSourceList: () => void;
  setSourceListOpen: (isOpen: boolean) => void;
  setActiveSource: (sourceId: string | null) => void;
  setActiveChatId: (chatId: string | null) => void;
  setSourceViewerWidth: (width: number) => void;
  setSourceList: (sources: Source[]) => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  isSourceListOpen: false, // Closed by default until sources are available
  activeSource: null,
  activeChatId: null,
  sourceViewerWidth: 600, // Default width for source viewer pane
  sourceList: [],
  toggleSourceList: () => set((state) => ({ isSourceListOpen: !state.isSourceListOpen })),
  setSourceListOpen: (isOpen) => set({ isSourceListOpen: isOpen }),
  setActiveSource: (sourceId) => set({ activeSource: sourceId }),
  setActiveChatId: (chatId) => set({ activeChatId: chatId }),
  setSourceViewerWidth: (width) => set({ sourceViewerWidth: width }),
  setSourceList: (sources) => set({ sourceList: sources }),
}));
