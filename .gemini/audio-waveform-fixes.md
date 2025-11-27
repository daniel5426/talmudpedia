# Audio Waveform Animation Fixes

## Summary
Fixed issues with the audio waveform animation visibility, background color, text alignment, and overlay positioning in the input areas.

## Changes Made

### 1. Fixed AudioWaveform Component
**File:** `/frontend/src/components/ui/audio-waveform.tsx`

- **Problem:** The previous implementation used `styled-jsx` which wasn't working correctly, and the dynamic keyframe injection was fragile.
- **Fix:** Rewrote the component to use a standard `<style>` tag injected into the render output.
- **Improvement:** Added base styling to the bars (width, height, color) to ensure they are visible even if animation fails.
- **Animation:** Used a simple, robust CSS keyframe animation (`waveform-anim`) defined in the style tag.

### 2. Corrected Overlay Background
**Files:** 
- `/frontend/src/components/DocumentSearchInputArea.tsx`
- `/frontend/src/components/ai-elements/prompt-input.tsx`

- **Problem:** The overlay was using `bg-background/80` (white transparent) or `bg-primary-soft/90`, which looked like a "white block" or didn't match the input area perfectly.
- **Fix:** Changed the overlay background to opaque `bg-primary-soft`.
- **Result:** The overlay now seamlessly blends with the input area, hiding the text behind it while showing the waveform.

### 3. Resolved Text Alignment Regression
**File:** `/frontend/src/components/ai-elements/prompt-input.tsx`

- **Problem:** The previous attempt to add the overlay in `PromptInputBody` by wrapping it in a `div` with `relative` broke the `contents` display mode required for `InputGroup` layout, causing text alignment issues.
- **Fix:** Reverted `PromptInputBody` to its original state.
- **Solution:** Moved the waveform overlay to the `InputGroup` level in `PromptInput`. This ensures the overlay is positioned correctly relative to the input group without interfering with the flex layout of the textarea and other elements.

### 4. Fixed Overlay Covering Tools
**File:** `/frontend/src/components/ai-elements/prompt-input.tsx`

- **Problem:** The overlay at the `InputGroup` level was covering the entire input block, including the footer tools (mic, stop button, etc.), making them unclickable.
- **Fix:** Added `relative z-20` to `PromptInputFooter` and `PromptInputAttachments`.
- **Result:** The tools and attachments now sit *above* the opaque waveform overlay (z-10). The overlay effectively masks only the textarea content, while keeping the controls accessible and visible.

## Verification
- **Waveform:** Should now be clearly visible with animated bars.
- **Background:** Should match the input area color exactly.
- **Layout:** Text alignment in the chat pane should be back to normal.
- **Interactivity:** Tools (mic, stop, submit) should be visible and clickable while recording.
