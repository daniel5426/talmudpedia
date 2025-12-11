import { httpClient } from "./http";
export interface LibraryNode {
  title: string;
  heTitle?: string;
  type: "category" | "book" | "text" | "section";
  children?: LibraryNode[];
  ref?: string;
  slug?: string;
  hasChildren?: boolean;
}

export interface LibrarySearchResult {
  title: string;
  heTitle?: string;
  ref?: string;
  slug?: string;
  path?: string[];
  path_he?: string[];
  type?: string;
  score?: number;
}

export const normalizeLibraryQuery = (query: string) => {
  if (!query) return "";
  const cleaned = query
    .toLowerCase()
    .replace(/[^0-9a-z\u0590-\u05ff\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned;
};

class LibraryService {
  private static VERSION = "2";
  rootPromise?: Promise<LibraryNode[]>;
  childPromises: Record<string, Promise<LibraryNode[]>> = {};
  searchPromises: Record<string, Promise<LibrarySearchResult[]>> = {};

  getRoot(): Promise<LibraryNode[]> {
    if (!this.rootPromise) {
      this.rootPromise = httpClient.get<LibraryNode[]>(`/api/library/menu?v=${LibraryService.VERSION}`);
    }
    return this.rootPromise;
  }

  getChildren(slug: string): Promise<LibraryNode[]> {
    if (!this.childPromises[slug]) {
      this.childPromises[slug] = httpClient.get<LibraryNode[]>(`/api/library/menu/${slug}?v=${LibraryService.VERSION}`);
    }
    return this.childPromises[slug];
  }

  search(query: string): Promise<LibrarySearchResult[]> {
    const key = normalizeLibraryQuery(query);
    if (!key) {
      return Promise.resolve([]);
    }
    if (!this.searchPromises[key]) {
      const params = new URLSearchParams({ q: key });
      this.searchPromises[key] = httpClient.get<LibrarySearchResult[]>(`/api/library/search?${params.toString()}`);
    }
    return this.searchPromises[key];
  }
}

export const libraryService = new LibraryService();

