import type { Metadata } from "next";
import { Head, Search } from "nextra/components";
import { Layout, Navbar } from "nextra-theme-docs";
import { getPageMap } from "nextra/page-map";
import type { ReactNode } from "react";
import "nextra-theme-docs/style.css";
import "./global.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://docs.agents24.dev";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Agents24 Docs",
    template: "%s | Agents24 Docs"
  },
  description:
    "Task-first documentation for building agents, retrieval flows, tools, and production-ready runtime integrations on Agents24."
};

const navbar = (
  <Navbar
    logo={<span>Agents24 Docs</span>}
    projectLink="https://github.com/daniel5426/talmudpedia"
  />
);

export default async function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <Head />
      <body>
        <Layout
          navbar={navbar}
          pageMap={await getPageMap()}
          docsRepositoryBase="https://github.com/daniel5426/talmudpedia/tree/main/docs-site/app"
          editLink="Edit this page"
          feedback={{
            content: "Report a docs gap",
            labels: "documentation"
          }}
          navigation
          search={<Search />}
          sidebar={{
            autoCollapse: true,
            defaultMenuCollapseLevel: 1,
            toggleButton: true
          }}
          nextThemes={{
            defaultTheme: "system",
            disableTransitionOnChange: true
          }}
        >
          {children}
        </Layout>
      </body>
    </html>
  );
}
