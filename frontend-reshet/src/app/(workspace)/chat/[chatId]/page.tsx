import { ChatPane } from "@/components/layout/ChatPane";

interface ChatPageProps {
  params: Promise<{ chatId: string }>;
}

export default async function ChatPage({ params }: ChatPageProps) {
  const { chatId } = await params;
  return <ChatPane chatId={chatId} />;
}
