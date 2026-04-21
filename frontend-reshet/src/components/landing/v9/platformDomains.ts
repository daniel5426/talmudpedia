import type { StaticImageData } from "next/image";

import agentsPageScreenshot from "../../../../public/platform_screenshot/agents.png";
import artifactScreenshot from "../../../../public/platform_screenshot/Artifact.png";
import deploymentScreenshot from "../../../../public/platform_screenshot/deployment.png";
import governanceScreenshot from "../../../../public/platform_screenshot/governance.png";
import knowledgeScreenshot from "../../../../public/platform_screenshot/knowledge.png";
import monitoringScreenshot from "../../../../public/platform_screenshot/Monitoring.png";

export const PLATFORM_DOMAINS = [
  {
    title: "Agent Graphs",
    eyebrow: "Execution",
    heading: "Design and operate graph-based agent systems without splitting authoring from runtime.",
    body: "Move from prompt chains to explicit execution graphs, tool orchestration, and governed runtime behavior in one surface.",
    points: ["Graph authoring", "Tool contracts", "Runtime execution", "Trace visibility"],
    statLabel: "Active graphs",
    statValue: "124",
  },
  {
    title: "Knowledge",
    eyebrow: "Retrieval",
    heading: "Attach structured knowledge pipelines directly to the platform that serves production agents.",
    body: "Keep ingestion, retrieval, source management, and operator-level control in the same operating layer as your deployed agents.",
    points: ["Source pipelines", "Operator tuning", "Index governance", "Answer grounding"],
    statLabel: "Indexed sources",
    statValue: "18.4K",
  },
  {
    title: "Governance",
    eyebrow: "Control",
    heading: "Track cost, permissions, and model behavior with explicit platform rules instead of ad-hoc conventions.",
    body: "Make runtime budgets, model policy, resource controls, and operator boundaries first-class platform primitives.",
    points: ["Quota policy", "Scope control", "Model routing", "Usage accounting"],
    statLabel: "Guardrails enforced",
    statValue: "31",
  },
  {
    title: "Deployments",
    eyebrow: "Runtime",
    heading: "Move from local iteration to deployed runtime surfaces without losing visibility or control.",
    body: "Ship hosted experiences, embedded runtimes, and managed app surfaces from the same platform backbone.",
    points: ["Hosted apps", "Embedded runtime", "Preview flow", "Release controls"],
    statLabel: "Live environments",
    statValue: "52",
  },
  {
    title: "Monitoring",
    eyebrow: "Operations",
    heading: "Monitor organization activity, token accounting, and resource health from one operator-facing stats surface.",
    body: "Track users, agent runs, spend coverage, queue behavior, and resource inventory through a organization-scoped monitoring layer built for operational clarity.",
    points: ["Usage coverage", "Agent trends", "Resource inventory", "Operator drilldowns"],
    statLabel: "Tracked metrics",
    statValue: "4 sections",
  },
  {
    title: "Artifacts",
    eyebrow: "Runtime Units",
    heading: "Author reusable execution units with revision history, test runs, and explicit publish controls.",
    body: "Treat artifacts as the shared execution substrate for tools, agent nodes, and RAG operators, with immutable revisions and ordered run telemetry.",
    points: ["Revision snapshots", "Draft testing", "Run events", "Published pinning"],
    statLabel: "Runtime kinds",
    statValue: "3",
  },
] as const;

export const DOMAIN_SCREENSHOTS: Record<(typeof PLATFORM_DOMAINS)[number]["title"], StaticImageData> = {
  "Agent Graphs": agentsPageScreenshot,
  Knowledge: knowledgeScreenshot,
  Governance: governanceScreenshot,
  Deployments: deploymentScreenshot,
  Monitoring: monitoringScreenshot,
  Artifacts: artifactScreenshot,
};

const DOMAIN_SCROLL_LEAD_IN = 0.14;
const DOMAIN_SCROLL_TAIL = 0.12;
const DOMAIN_SCROLL_HOLD_RATIO = 0.58;

function createDomainScrollModel(domainCount: number) {
  if (domainCount <= 1) {
    return {
      inputRange: [0, 1],
      outputRange: [0, 0],
      clickTargets: [0.5],
    };
  }

  const transitionCount = domainCount - 1;
  const transitionSpan = (1 - DOMAIN_SCROLL_LEAD_IN - DOMAIN_SCROLL_TAIL) / transitionCount;
  const inputRange = [0, DOMAIN_SCROLL_LEAD_IN];
  const outputRange = [0, 0];
  const clickTargets = [DOMAIN_SCROLL_LEAD_IN * 0.5];

  for (let index = 0; index < transitionCount; index += 1) {
    const currentValue = index / transitionCount;
    const nextValue = (index + 1) / transitionCount;
    const plateauEnd = DOMAIN_SCROLL_LEAD_IN + index * transitionSpan + transitionSpan * DOMAIN_SCROLL_HOLD_RATIO;
    const nextHoldStart = DOMAIN_SCROLL_LEAD_IN + (index + 1) * transitionSpan;

    inputRange.push(plateauEnd, nextHoldStart);
    outputRange.push(currentValue, nextValue);

    if (index < transitionCount - 1) {
      clickTargets.push(nextHoldStart + (transitionSpan * DOMAIN_SCROLL_HOLD_RATIO) / 2);
    }
  }

  clickTargets.push(1 - DOMAIN_SCROLL_TAIL * 0.5);

  inputRange.push(1);
  outputRange.push(1);

  return { inputRange, outputRange, clickTargets };
}

export const PLATFORM_DOMAIN_SCROLL_MODEL = createDomainScrollModel(PLATFORM_DOMAINS.length);

export function getPlatformDomainsSceneHeight(isMobile: boolean) {
  const baseHeight = isMobile ? 120 : 220;
  const increment = isMobile ? 70 : 120;
  return `${baseHeight + PLATFORM_DOMAINS.length * increment}vh`;
}
