# Pipeline UI & Execution Mode Fixes

## Overview
This document details the critical UI and logic fixes implemented in the Pipeline Builder to ensure robust execution mode behavior, correct rendering of custom operators, and stable state transitions.

## 1. Custom Operator Edge Visibility

### Problem
Edges connected to custom operators were disappearing after a page reload (but appearing correctly when navigating from the table).
- **Root Cause**: The `PipelineBuilder` component was initializing with partial data because the data fetch in `page.tsx` was firing before the `TenantContext` was fully ready. This resulted in `initialNodes` lacking the correct input/output type specifications from the registry, so React Flow handles were not rendered.
- **Fix**: 
  - Added a strict check `if (!currentTenant) return` in `page.tsx` to delay data fetching until the tenant context is fully initialized.
  - Updated node hydration logic to use `specsRes` (flat operator specifications) which correctly resolves custom operator schemas.

## 2. Execution Mode Exit "Loop" (The "Click Twice" Bug)

### Problem
Users had to click the "Exit Execution Mode" button twice to actually open the catalog. The first click seemed to do nothing or quickly toggle state.
- **Root Cause**: The `handleExitExecutionMode` function was using `window.history.replaceState` to clear the `jobId` URL parameter. However, Next.js `useSearchParams` does not react to `history` API calls immediately. 
  - This caused the local `jobIdParam` to remain "stale" (holding the old ID).
  - A synchronization `useEffect` (depending on `jobIdParam` and `runningJobId`) observed the mismatch: `jobIdParam` (stale/present) vs `runningJobId` (just cleared to null).
  - The effect incorrectly "restored" the running state from the stale URL param, cancelling the exit.
- **Fix**: 
  - Switched to `router.replace` to properly update Next.js router state.
  - Refactored the synchronization `useEffect` to depend **strictly on `jobIdParam`** (ignoring local state changes). This ensures we only sync when the URL actually changes (navigation), preventing local state clearing from triggering a restore loop.

## 3. Catalog Toggle Reliability

### Problem
The node catalog sidebar would sometimes fail to open or flicker when exiting execution mode.
- **Root Cause**: Reliance on simple execution mode prop toggling sometimes hit race conditions with React's render cycle, causing the "Show Catalog" state to get out of sync.
- **Fix**: 
  - Implemented a `useRef`-based tracker (`prevExecutionMode`) in `PipelineBuilder.tsx`.
  - The `useEffect` now strictly compares `prevExecutionMode.current !== isExecutionMode` to detect actual mode transitions.
  - When `isExecutionMode` transitions to `false`, the catalog is explicitly forced open (`setIsCatalogVisible(true)`).

## 4. Auto-Exit on Job Completion

### Problem
The execution mode would automatically exit (and the catalog would open) immediately when a job finished. This prevented users from viewing the visual execution results (green rings, checkmarks).
- **Fix**: Removed the logic that called `setRunningJobId(null)` upon job completion. Users now stay in execution mode to inspect results and must manually exit to return to editing.

## Summary of Changes
- **`src/app/admin/pipelines/[id]/page.tsx`**: 
  - Reduced dependencies in `useEffect` hooks to prevent cycles.
  - Used `router.replace` for reliable URL updates.
  - Added guards for `currentTenant`.
- **`src/components/pipeline/PipelineBuilder.tsx`**:
  - Implemented reliable state tracking for catalog visibility.
  - Removed conflicting animations causing flickers.

## 5. Execution Data Loading Experience

### Problem
When clicking a node in execution mode, there was a delay before selection visual feedback because the UI waited for the execution data to be available (or checked for it) before showing the details panel. This made the application feel unresponsive ("nothing happens").
- **Fix**: 
  - Decoupled node selection from data availability. Selection is now immediate in `PipelineBuilder`.
  - Introduced `ExecutionDetailsSkeleton` component.
  - in `PipelineBuilder.tsx`, if a node is selected in execution mode but its `executionStep` data is not yet available (loading or pending), the `ExecutionDetailsSkeleton` is instantly shown instead of checking for data presence or falling back to the `ConfigPanel`.
