import { act, renderHook } from "@testing-library/react";

import { useBuilderPreviewTransport } from "@/features/apps-builder/preview/useBuilderPreviewTransport";
import { normalizeBuilderPreviewRoute } from "@/features/apps-builder/preview/previewTransport";
import {
  extractAppsBuilderPreviewRoutes,
  normalizeAppsBuilderPreviewRoute,
} from "@/services/apps-builder-preview-routes";

describe("useBuilderPreviewTransport runtime token stability", () => {
  it("does not treat builder preview proxy paths as app routes", () => {
    expect(normalizeBuilderPreviewRoute("/public/apps-builder/draft-dev/sessions/session-1/preview")).toBe("/");
    expect(normalizeBuilderPreviewRoute("/public/apps-builder/draft-dev/sessions/session-1/preview/chat")).toBe("/chat");
    expect(normalizeBuilderPreviewRoute("/public/apps-builder/draft-dev/sessions/session-1/preview/assets/index.js")).toBe("/");
  });

  it("uses one normalization contract for route input, transport, and route discovery", () => {
    expect(normalizeAppsBuilderPreviewRoute("chat?tab=1")).toBe("/chat");
    expect(normalizeAppsBuilderPreviewRoute("/chat/")).toBe("/chat");
    expect(normalizeAppsBuilderPreviewRoute("/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/status")).toBe("/");
    expect(normalizeBuilderPreviewRoute("chat?tab=1")).toBe("/chat");
  });

  it("extracts static app routes without leaking assets or dynamic route templates", () => {
    expect(extractAppsBuilderPreviewRoutes({
      "src/app/page.tsx": "export default function Home() { return <a href=\"/about\">About</a>; }",
      "src/app/settings/page.tsx": "navigate('/settings/profile')",
      "src/app/users/[id]/page.tsx": "export default function User() { return null; }",
      "src/pages/contact.tsx": "<Route path=\"/contact\" />",
      "src/pages/api/ping.ts": "export default function handler() {}",
      "src/App.tsx": "<img src=\"/assets/logo.png\" />",
    })).toEqual(["/", "/about", "/contact", "/settings", "/settings/profile"]);
  });

  it("extracts relative React Router paths and route-object paths", () => {
    expect(extractAppsBuilderPreviewRoutes({
      "src/App.tsx": `
        const routes = [
          { path: "dashboard", element: <Dashboard /> },
          { path: "settings/profile", element: <Profile /> },
          { path: ":userId", element: <User /> },
        ];
        export default function App() {
          return (
            <Routes>
              <Route index element={<Home />} />
              <Route path="reports" element={<Reports />} />
              <Link to="billing">Billing</Link>
              <a href="https://example.com">External</a>
              <a href="./assets/logo.png">Asset</a>
            </Routes>
          );
        }
      `,
    })).toEqual(["/", "/billing", "/dashboard", "/reports", "/settings/profile"]);
  });

  it("keeps the current document URL when only the preview runtime_token rotates", () => {
    const { result, rerender } = renderHook(
      (props: { previewBaseUrl: string }) =>
        useBuilderPreviewTransport({
          sessionId: "session-1",
          previewBaseUrl: props.previewBaseUrl,
          previewRoute: "/",
          previewTransportGeneration: 1,
          livePreviewStatus: "ready",
          livePreviewLastSuccessfulBuildId: "build-1",
          livePreviewError: null,
          hardReloadToken: 0,
          draftDevStatus: "serving",
          lifecyclePhase: "running",
          lastError: null,
        }),
      {
        initialProps: {
          previewBaseUrl: "https://preview.local/sandbox/session-1/?runtime_token=token-a",
        },
      },
    );

    const initialTransportKey = result.current.transportKey;
    expect(initialTransportKey).toBe("session-1:1000");
    const initialDocumentUrl = result.current.documentUrl;
    expect(initialDocumentUrl).toContain("runtime_token=token-a");

    act(() => {
      result.current.markFrameUsable(initialTransportKey);
    });

    rerender({
      previewBaseUrl: "https://preview.local/sandbox/session-1/?runtime_token=token-b",
    });

    expect(result.current.transportKey).toBe(initialTransportKey);
    expect(result.current.documentUrl).toBe(initialDocumentUrl);
  });

  it("updates the document URL when the preview route changes within the same session", () => {
    const { result, rerender } = renderHook(
      (props: { previewRoute: string }) =>
        useBuilderPreviewTransport({
          sessionId: "session-1",
          previewBaseUrl: "https://preview.local/sandbox/session-1/",
          previewRoute: props.previewRoute,
          previewTransportGeneration: 1,
          livePreviewStatus: "ready",
          livePreviewLastSuccessfulBuildId: "build-1",
          livePreviewError: null,
          hardReloadToken: 0,
          draftDevStatus: "serving",
          lifecyclePhase: "running",
          lastError: null,
        }),
      {
        initialProps: {
          previewRoute: "/",
        },
      },
    );

    const initialTransportKey = result.current.transportKey;
    const initialDocumentUrl = result.current.documentUrl;

    act(() => {
      result.current.markFrameUsable(initialTransportKey);
    });

    rerender({
      previewRoute: "/chat",
    });

    expect(result.current.transportKey).toBe(initialTransportKey);
    expect(result.current.documentUrl).not.toBe(initialDocumentUrl);
    expect(result.current.documentUrl).toContain("preview_route=%2Fchat");
  });
});
