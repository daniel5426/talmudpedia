export interface OpenSourceOptions {
  pagesAfter?: number | null;
  totalSegments?: number | null;
}

/**
 * Centrally handles opening a source and setting up its highlighting/pagination metadata.
 * Use this instead of calling setActiveSource directly from UI components.
 */
export async function openSource(targetRef: string, options: OpenSourceOptions = {}) {
  try {
    // Import the store dynamically to avoid circular dependencies and ensure we're on the client
    const { useLayoutStore } = await import('@/lib/store/useLayoutStore');
    const { setActiveSource, setSourceListOpen } = useLayoutStore.getState();

    // Set the active source with standard options
    setActiveSource(targetRef, {
      pagesAfter: options.pagesAfter ?? 2,
      totalSegments: options.totalSegments ?? 1
    });

    // Ensure source viewer is visible/open if needed by layout
    // (Optional: depending on whether we want to auto-open if it's closed)
  } catch (error) {
    console.error("Failed to open source:", error);
  }
}
