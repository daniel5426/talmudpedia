import type { TemplateThread } from "./types";

export const HISTORY_PAGE_SIZE = 5;

export const INITIAL_THREADS: TemplateThread[] = [
  {
    id: "thread-1",
    title: "Design a smarter onboarding flow",
    preview: "I drafted a first-pass onboarding loop with two tool checks inline.",
    updatedAt: "2m ago",
    messages: [
      {
        id: "thread-1-user-1",
        role: "user",
        createdAt: "2026-03-15T12:00:00.000Z",
        text: "Design a cleaner onboarding flow for a B2B AI product.",
      },
      {
        id: "thread-1-assistant-1",
        role: "assistant",
        createdAt: "2026-03-15T12:00:10.000Z",
        blocks: [
          {
            id: "thread-1-assistant-1-text-1",
            kind: "text",
            content:
              "Start with a two-step reveal. Let the first screen establish trust and value before asking for workspace details.",
          },
          {
            id: "thread-1-assistant-1-task-1",
            kind: "task",
            title: "Inspecting current onboarding friction",
            status: "done",
            items: [
              "Compared the current form density against the playground-style rhythm.",
              "Flagged the account setup step as too front-loaded.",
            ],
            files: ["onboarding-audit.md"],
          },
          {
            id: "thread-1-assistant-1-text-2",
            kind: "text",
            content:
              "Then move the setup details into contextual follow-ups once the user has already completed the first prompt and seen a useful response.",
          },
          {
            id: "thread-1-assistant-1-sources",
            kind: "sources",
            title: "References used",
            sources: [
              { id: "src-1", label: "Playground layout notes", href: "#" },
              { id: "src-2", label: "Template IA decisions", href: "#" },
            ],
          },
        ],
      },
    ],
  },
  {
    id: "thread-2",
    title: "Build a tenant metrics dashboard",
    preview: "We broke the dashboard into hero stats, table, and review queue.",
    updatedAt: "18m ago",
    messages: [
      {
        id: "thread-2-user-1",
        role: "user",
        createdAt: "2026-03-15T11:40:00.000Z",
        text: "Sketch a tenant metrics dashboard with approvals and queue health.",
      },
      {
        id: "thread-2-assistant-1",
        role: "assistant",
        createdAt: "2026-03-15T11:40:08.000Z",
        blocks: [
          {
            id: "thread-2-assistant-1-text-1",
            kind: "text",
            content:
              "Use a top-level summary strip, then a split layout with queue health on the left and approval work on the right.",
          },
          {
            id: "thread-2-assistant-1-reasoning",
            kind: "reasoning",
            title: "Why this works",
            steps: [
              "The top strip gives fast operational context.",
              "The split body prevents the dashboard from collapsing into a generic card wall.",
              "Approvals should stay immediately actionable, not buried under charts.",
            ],
          },
          {
            id: "thread-2-assistant-1-task-1",
            kind: "task",
            title: "Checking reusable dashboard primitives",
            status: "done",
            items: [
              "Mapped stats to cards.",
              "Mapped approvals to a paginated table block.",
            ],
          },
        ],
      },
    ],
  },
  {
    id: "thread-3",
    title: "Polish a chat-first settings page",
    preview: "We kept the content editor minimal and pushed secondary actions into drawers.",
    updatedAt: "1h ago",
    messages: [
      {
        id: "thread-3-user-1",
        role: "user",
        createdAt: "2026-03-15T10:30:00.000Z",
        text: "How should a chat-first settings page feel?",
      },
      {
        id: "thread-3-assistant-1",
        role: "assistant",
        createdAt: "2026-03-15T10:30:06.000Z",
        blocks: [
          {
            id: "thread-3-assistant-1-text-1",
            kind: "text",
            content:
              "Keep the primary settings inline and conversational. Push destructive and rarely used actions into sheets or dialogs.",
          },
        ],
      },
    ],
  },
  {
    id: "thread-4",
    title: "Refine thread handoff state",
    preview: "We should preserve context while making active handoffs obvious.",
    updatedAt: "3h ago",
    messages: [],
  },
  {
    id: "thread-5",
    title: "Agent trace viewer notes",
    preview: "Trace should stay one click away from assistant actions.",
    updatedAt: "Yesterday",
    messages: [],
  },
  {
    id: "thread-6",
    title: "Published app auth shell",
    preview: "Separate app shell auth from thread/session content.",
    updatedAt: "Yesterday",
    messages: [],
  },
  {
    id: "thread-7",
    title: "Search-driven welcome state",
    preview: "The empty state should invite prompting, not explain the product.",
    updatedAt: "2d ago",
    messages: [],
  },
];

export const EMPTY_SUGGESTIONS = [
  "Summarize recent activity for the selected client",
  "Show bank concentration for this client",
  "Explain deal 200462 for this client",
  "Compare deal 200462 against market context",
];
