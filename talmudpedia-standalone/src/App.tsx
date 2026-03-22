import { ClassicChatApp } from "@/features/classic-chat/classic-chat-app";
import { WidgetLabPage } from "@/features/prico-widgets/widget-lab-page";

export function App() {
  if (typeof window !== "undefined" && window.location.pathname === "/widget-lab") {
    return <WidgetLabPage />;
  }
  return <ClassicChatApp />;
}

export default App;
