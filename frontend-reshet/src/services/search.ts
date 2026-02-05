import { httpClient } from "./http";

export interface SearchResult {
  id: string;
  snippet: string;
  metadata: any;
  title?: string;
  score: number;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface SearchParams {
  query: string;
  limit?: number;
}

class SearchService {
  async search(params: SearchParams): Promise<SearchResponse> {
    return httpClient.post<SearchResponse>("/search", params);
  }

  async searchSource(query: string): Promise<SearchResponse> {
    const params = new URLSearchParams({ q: query });
    return httpClient.get<SearchResponse>(`/search?${params.toString()}`);
  }
}

export const searchService = new SearchService();
