type SelectedText = { text: string; sourceRef?: string } | null;

type Store = {
  selectedText: SelectedText;
  setSelectedText: (value: SelectedText) => void;
};

const state: Store = {
  selectedText: null,
  setSelectedText: (value: SelectedText) => {
    state.selectedText = value;
  },
};

export function useLayoutStore<T>(selector: (store: Store) => T): T {
  return selector(state);
}
