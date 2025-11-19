import { create } from 'zustand';

interface LayoutState {
  isSourceListOpen: boolean;
  activeSource: string | null;
  toggleSourceList: () => void;
  setSourceListOpen: (isOpen: boolean) => void;
  setActiveSource: (sourceId: string | null) => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  isSourceListOpen: false, // Closed by default until sources are available
  activeSource: null,
  toggleSourceList: () => set((state) => ({ isSourceListOpen: !state.isSourceListOpen })),
  setSourceListOpen: (isOpen) => set({ isSourceListOpen: isOpen }),
  setActiveSource: (sourceId) => set({ activeSource: sourceId }),
}));
