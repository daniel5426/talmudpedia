import { LegalPage } from "@/components/marketing/legal-page";

const TERMS_SECTIONS = [
  {
    title: "Beta status",
    paragraphs: [
      "AGENTS24 is currently offered as a beta product. Features may change, be interrupted, or be removed without prior notice while the platform is still under active development and testing.",
      "Access may be limited, suspended, or revoked at any time, especially where use creates operational, security, legal, or abuse concerns.",
    ],
  },
  {
    title: "Acceptable use",
    paragraphs: [
      "You may not use the platform to violate law, infringe rights, interfere with service availability, attempt unauthorized access, or run workloads that are abusive, deceptive, or harmful.",
      "You remain responsible for the prompts, data, credentials, content, and workflows you configure or submit through the platform.",
    ],
  },
  {
    title: "No warranty",
    paragraphs: [
      "The service is provided on an 'as is' and 'as available' basis. To the maximum extent allowed by law, we disclaim warranties of merchantability, fitness for a particular purpose, and non-infringement.",
      "We do not guarantee uninterrupted availability, error-free behavior, or that platform outputs will be accurate, complete, or suitable for production reliance without your own review.",
    ],
  },
  {
    title: "Liability and changes",
    paragraphs: [
      "To the maximum extent allowed by law, AGENTS24 will not be liable for indirect, incidental, special, consequential, or lost-profit damages arising from use of the platform.",
      "We may update these terms as the beta evolves. Continued use after an update means you accept the revised terms.",
    ],
  },
] as const;

export default function TermsPage() {
  return (
    <LegalPage
      eyebrow="Terms"
      title="Terms of Service"
      description="These terms govern access to the AGENTS24 beta platform, including operator tooling, hosted runtime surfaces, and related contact flows."
      effectiveDate="April 12, 2026"
      sections={[...TERMS_SECTIONS]}
    />
  );
}
