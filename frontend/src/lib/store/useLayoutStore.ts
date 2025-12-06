import { create } from 'zustand';
import { persist } from 'zustand/middleware';

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

export interface SelectedText {
  id: string;
  text: string;
  sourceRef?: string;
}

interface LayoutState {
  isSourceListOpen: boolean;
  activeSource: string | null;
  activeChatId: string | null;
  sourceViewerWidth: number;
  sourceList: Source[];
  selectedText: SelectedText | null;
  isLibraryMode: boolean;
  libraryPathTitles: string[];
  refreshTrigger: number;
  toggleSourceList: () => void;
  setSourceListOpen: (isOpen: boolean) => void;
  setActiveSource: (sourceId: string | null) => void;
  setActiveChatId: (chatId: string | null) => void;
  setSourceViewerWidth: (width: number) => void;
  setSourceList: (sources: Source[]) => void;
  setSelectedText: (text: SelectedText | null) => void;
  setLibraryMode: (isLibraryMode: boolean) => void;
  setLibraryPathTitles: (titles: string[]) => void;
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      isSourceListOpen: false, // Closed by default until sources are available
      activeSource: null,
      activeChatId: null,
      sourceViewerWidth: 600, // Default width for source viewer pane
      sourceList: [],
      selectedText: null,
      isLibraryMode: false,
      libraryPathTitles: [],
      refreshTrigger: 0,
      toggleSourceList: () => set((state) => ({ isSourceListOpen: !state.isSourceListOpen })),
      setSourceListOpen: (isOpen) => set({ isSourceListOpen: isOpen }),
      setActiveSource: (sourceId) => set((state) => ({ activeSource: sourceId, refreshTrigger: state.refreshTrigger + 1 })),
      setActiveChatId: (chatId) => set({ activeChatId: chatId }),
      setSourceViewerWidth: (width) => set({ sourceViewerWidth: width }),
      setSourceList: (sources) => set({ sourceList: sources }),
      setSelectedText: (text) => set({ selectedText: text }),
      setLibraryMode: (isLibraryMode) => set({ isLibraryMode }),
      setLibraryPathTitles: (titles) => set({ libraryPathTitles: titles }),
    }),
    {
      name: 'layout-storage',
      partialize: (state) => ({
        activeSource: state.activeSource,
        isSourceListOpen: state.isSourceListOpen,
        sourceViewerWidth: state.sourceViewerWidth,
        isLibraryMode: state.isLibraryMode,
        libraryPathTitles: state.libraryPathTitles,
      }),
    }
  )
);
