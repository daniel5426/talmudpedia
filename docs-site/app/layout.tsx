import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Source_Sans_3 } from "next/font/google";
import { Head, Search } from "nextra/components";
import { Footer, Layout, Navbar } from "nextra-theme-docs";
import { getPageMap } from "nextra/page-map";
import type { ReactNode } from "react";
import "nextra-theme-docs/style.css";
import "./global.css";

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["500", "600", "700"]
});

const sans = Source_Sans_3({
  subsets: ["latin"],
  variable: "--font-sans"
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"]
});

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

const banner = (
  <span>
    These docs are built in public. Every gap found here becomes product work.
  </span>
);

const navbar = (
  <Navbar
    logo={
      <span className="brand-lockup">
        <span className="brand-mark" aria-hidden="true">
          A24
        </span>
        <span className="brand-copy">
          <strong>Agents24 Docs</strong>
          <small>Build, validate, ship</small>
        </span>
      </span>
    }
    projectLink="https://github.com/daniel5426/talmudpedia"
  />
);

const footer = (
  <Footer>
    <span>Agents24 public docs foundation.</span>
    <a href="https://agents24.dev">agents24.dev</a>
  </Footer>
);

export default async function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html
      lang="en"
      dir="ltr"
      suppressHydrationWarning
      className={`${display.variable} ${sans.variable} ${mono.variable}`}
    >
      <Head
        color={{
          hue: 192,
          saturation: 56
        }}
      >
        <meta
          name="theme-color"
          media="(prefers-color-scheme: light)"
          content="#f8f3eb"
        />
        <meta
          name="theme-color"
          media="(prefers-color-scheme: dark)"
          content="#08131a"
        />
      </Head>
      <body>
        <Layout
          banner={banner}
          navbar={navbar}
          footer={footer}
          pageMap={await getPageMap()}
          docsRepositoryBase="https://github.com/daniel5426/talmudpedia/tree/main/docs-site/app"
          darkMode
          editLink="Edit this page"
          feedback={{
            content: "Report a docs gap",
            labels: "documentation"
          }}
          navigation
          search={<Search placeholder="Search Agents24 docs…" />}
          sidebar={{
            autoCollapse: true,
            defaultMenuCollapseLevel: 1,
            toggleButton: true
          }}
          themeSwitch={{
            dark: "Night",
            light: "Day",
            system: "System"
          }}
          nextThemes={{
            defaultTheme: "system",
            disableTransitionOnChange: true
          }}
          toc={{
            title: "On this page",
            backToTop: "Back to top"
          }}
        >
          {children}
        </Layout>
      </body>
    </html>
  );
}
