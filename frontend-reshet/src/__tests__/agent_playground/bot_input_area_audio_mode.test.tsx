import { render, screen, waitFor } from "@testing-library/react";
import { useRef } from "react";

import { BotInputArea } from "@/components/BotInputArea";

jest.mock("nanoid", () => ({
  nanoid: () => "mock-id",
}));

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}));

jest.mock("@/lib/store/useLayoutStore", () => ({
  useLayoutStore: (selector: (state: any) => any) =>
    selector({
      selectedText: null,
      setSelectedText: jest.fn(),
    }),
}));

jest.mock("@/components/WorkflowStateSettingsDialog", () => ({
  WorkflowStateSettingsDialog: () => null,
}));

function TestHarness({
  workflowInputs,
}: {
  workflowInputs: Array<{ key: string; type: string; enabled: boolean }>
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  return (
    <BotInputArea
      textareaRef={textareaRef}
      handleSubmit={jest.fn()}
      workflowInputs={workflowInputs as any}
      stateVariables={[]}
    />
  );
}

describe("BotInputArea audio input mode", () => {
  it("shows the mic only when workflow audio is enabled", async () => {
    const baseInputs = [
      { key: "text", type: "string", enabled: true },
      { key: "files", type: "list", enabled: true },
      { key: "audio", type: "list", enabled: false },
      { key: "images", type: "list", enabled: false },
    ];

    const { rerender } = render(<TestHarness workflowInputs={baseInputs} />);

    await waitFor(() => {
      expect(screen.queryByLabelText("Record audio input")).not.toBeInTheDocument();
    });

    rerender(
      <TestHarness
        workflowInputs={[
          ...baseInputs.slice(0, 2),
          { key: "audio", type: "list", enabled: true },
          { key: "images", type: "list", enabled: false },
        ]}
      />
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Record audio input")).toBeInTheDocument();
    });
  });
});
