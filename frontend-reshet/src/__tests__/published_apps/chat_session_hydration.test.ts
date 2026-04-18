import { createSessionContainer } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat.session-state";
import { shouldApplyHydratedSessionState } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat";

describe("chat session hydration guard", () => {
  it("skips force-reload hydration while a newer send is already in flight", () => {
    const session = createSessionContainer("session-1");
    session.isSendingRef.current = true;

    expect(shouldApplyHydratedSessionState(session, { forceReload: true })).toBe(false);
  });

  it("allows normal hydration when no newer send is active", () => {
    const session = createSessionContainer("session-1");

    expect(shouldApplyHydratedSessionState(session, { forceReload: true })).toBe(true);
    expect(shouldApplyHydratedSessionState(session, { forceReload: false })).toBe(true);
  });
});
