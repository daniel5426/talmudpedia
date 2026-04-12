import { create } from 'zustand';

interface HeaderState {
  scrolled: boolean;
  onSelectDomain: ((index: number) => void) | null;
  setScrolled: (scrolled: boolean) => void;
  setOnSelectDomain: (onSelectDomain: ((index: number) => void) | null) => void;
}

export const useHeaderStore = create<HeaderState>((set) => ({
  scrolled: false,
  onSelectDomain: null,
  setScrolled: (scrolled) => set({ scrolled }),
  setOnSelectDomain: (onSelectDomain) => set({ onSelectDomain }),
}));
