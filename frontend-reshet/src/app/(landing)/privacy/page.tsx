import { LegalPage } from "@/components/marketing/legal-page";

const PRIVACY_SECTIONS = [
  {
    title: "What we collect",
    paragraphs: [
      "We collect the information you submit directly, such as your name, email address, company or use case, and any message you send through the contact or access-request forms.",
      "When you use the platform, we may also collect operational data such as account details, authentication events, usage activity, and runtime telemetry needed to operate, secure, and improve the service.",
    ],
  },
  {
    title: "How we use it",
    paragraphs: [
      "We use the information to review access requests, respond to support or feedback messages, provide the platform, investigate abuse, and improve reliability and product quality.",
      "We do not sell your personal information. We use service providers only where needed to host the app, authenticate users, process email delivery, and monitor system health.",
    ],
  },
  {
    title: "Retention and security",
    paragraphs: [
      "We keep information for as long as it is reasonably needed to operate the beta, comply with legal obligations, resolve disputes, and maintain security records.",
      "We apply reasonable technical and organizational measures to protect the platform, but no system can guarantee absolute security.",
    ],
  },
  {
    title: "Your choices",
    paragraphs: [
      "You can contact us to ask about access, corrections, or deletion requests relating to the information you submitted directly.",
      "Because the product is still in beta, some self-serve privacy controls may not yet be available in-product.",
    ],
  },
] as const;

export default function PrivacyPage() {
  return (
    <LegalPage
      eyebrow="Privacy"
      title="Privacy Policy"
      description="This policy explains how AGENTS24 handles contact submissions, beta access data, and platform usage information."
      effectiveDate="April 12, 2026"
      sections={[...PRIVACY_SECTIONS]}
    />
  );
}
