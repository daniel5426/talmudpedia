import { httpClient } from "./http";

export interface SourcePageData {
  ref: string;
  he_ref?: string;
  full_he_ref?: string;
  segments: string[];
  highlight_index: number | null;
  highlight_indices?: number[];
}

export interface MultiPageTextData {
  pages: SourcePageData[];
  main_page_index: number;
  index_title: string;
  full_he_ref?: string;
  he_title?: string;
  he_ref?: string;
  heRef?: string;
  version_title: string;
  language: string;
  can_load_more?: { top: boolean; bottom: boolean };
}

export interface SinglePageTextData {
  ref: string;
  index_title: string;
  he_title?: string;
  version_title: string;
  language: string;
  segments: string[];
  highlight_index: number | null;
  highlight_indices?: number[];
}

class SourceService {
  async getInitial(
    sourceId: string,
    pagesBefore = 0,
    pagesAfter = 2
  ): Promise<MultiPageTextData | SinglePageTextData> {
    const query = `?pages_before=${pagesBefore}&pages_after=${pagesAfter}`;
    return httpClient.get(`/source/${encodeURIComponent(sourceId)}${query}`);
  }

  async getBefore(
    ref: string,
    pagesBefore = 2
  ): Promise<MultiPageTextData | SinglePageTextData> {
    const query = `?pages_before=${pagesBefore}&pages_after=0`;
    return httpClient.get(`/source/${encodeURIComponent(ref)}${query}`);
  }

  async getAfter(
    ref: string,
    pagesAfter = 2
  ): Promise<MultiPageTextData | SinglePageTextData> {
    const query = `?pages_before=0&pages_after=${pagesAfter}`;
    return httpClient.get(`/source/${encodeURIComponent(ref)}${query}`);
  }
}

export const sourceService = new SourceService();
