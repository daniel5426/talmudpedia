"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import {
  Bot,
  CircleDashed,
  Command,
  Database,
  LayoutDashboard,
  MessageSquare,
  Search,
  Shield,
  Sparkles,
  Users,
  Waves,
} from "lucide-react";

type IconType = React.ComponentType<{ className?: string; size?: number }>;

interface NavItem {
  title: string;
  icon: IconType;
}

const NAV: NavItem[] = [
  { title: "Search", icon: Search },
  { title: "Dashboard", icon: LayoutDashboard },
  { title: "Users", icon: Users },
  { title: "Chats", icon: MessageSquare },
  { title: "Agents", icon: Bot },
  { title: "Knowledge", icon: Database },
  { title: "Security", icon: Shield },
];

const SUBNAV: Record<string, string[]> = {
  Search: ["Semantic", "Sources", "Saved"],
  Dashboard: ["Overview", "Signals", "Health"],
  Users: ["All Users", "Segments", "Permissions"],
  Chats: ["Recent", "Pinned", "Archived"],
  Agents: ["Registry", "Runs", "Templates"],
  Knowledge: ["Indexes", "Pipelines", "Embeddings"],
  Security: ["Policies", "Audit", "SSO"],
};

function Frame({ sidebar }: { sidebar: React.ReactNode }) {
  return (
    <section className="frame">
      <div className="frameTop">
        <i />
        <i />
        <i />
        <span>workspace.preview</span>
      </div>
      <div className="frameBody">
        {sidebar}
        <article className="mainGhost">
          <div className="line a" />
          <div className="line b" />
          <div className="line c" />
          <div className="line d" />
        </article>
      </div>
    </section>
  );
}

function MonumentSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  const activeIndex = NAV.findIndex((n) => n.title === active) + 1;
  return (
    <Frame
      sidebar={
        <aside className="sb monument">
          <div className="monumentHeader">
            <small>Monument</small>
            <strong>{String(activeIndex).padStart(2, "0")}</strong>
          </div>
          <div className="monumentStack">
            {NAV.map((n, i) => (
              <button
                key={n.title}
                onClick={() => setActive(n.title)}
                className={active === n.title ? "monumentItem active" : "monumentItem"}
                style={{ animationDelay: `${i * 45}ms` }}
              >
                <i>{String(i + 1).padStart(2, "0")}</i>
                <span>{n.title}</span>
              </button>
            ))}
          </div>
        </aside>
      }
    />
  );
}

function RibbonCodeSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  return (
    <Frame
      sidebar={
        <aside className="sb ribbonCode">
          <div className="ribbonColumn">RIBBON.CODE</div>
          <div className="ribbonMain">
            {NAV.map((n, i) => (
              <button
                key={n.title}
                onClick={() => setActive(n.title)}
                className={active === n.title ? "ribbonItem active" : "ribbonItem"}
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <n.icon size={12} />
                <span>{n.title}</span>
              </button>
            ))}
          </div>
        </aside>
      }
    />
  );
}

function OrbitSliceSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  const activeIndex = Math.max(0, NAV.findIndex((n) => n.title === active));
  return (
    <Frame
      sidebar={
        <aside className="sb orbitSlice">
          <div className="orbitDial" style={{ transform: `translate(-50%, -50%) rotate(${activeIndex * 22}deg)` }}>
            <div />
            <div />
            <div />
            <div />
          </div>
          <div className="orbitList">
            {NAV.map((n, i) => (
              <button
                key={n.title}
                onClick={() => setActive(n.title)}
                className={active === n.title ? "orbitRow active" : "orbitRow"}
                style={{ animationDelay: `${i * 35}ms` }}
              >
                <n.icon size={11} />
                <span>{n.title}</span>
              </button>
            ))}
          </div>
        </aside>
      }
    />
  );
}

function SwissGridSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  return (
    <Frame
      sidebar={
        <aside className="sb swiss">
          <div className="swissMark">/ SWISS GRID /</div>
          <div className="swissMatrix">
            {NAV.map((n, i) => (
              <button
                key={n.title}
                onClick={() => setActive(n.title)}
                className={active === n.title ? "swissCell active" : "swissCell"}
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <b>{String(i + 1).padStart(2, "0")}</b>
                <span>{n.title}</span>
                <n.icon size={11} />
              </button>
            ))}
          </div>
        </aside>
      }
    />
  );
}

function SoftGlassSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  const [query, setQuery] = React.useState("");
  const filtered = NAV.filter((n) => n.title.toLowerCase().includes(query.toLowerCase()));
  return (
    <Frame
      sidebar={
        <aside className="sb softGlass">
          <div className="glassAura" />
          <div className="glassHead">
            <Sparkles size={12} />
            <span>Soft Glass</span>
          </div>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="filter" className="glassInput" />
          <div className="glassStack">
            {filtered.map((n, i) => (
              <button
                key={n.title}
                onClick={() => setActive(n.title)}
                className={active === n.title ? "glassItem active" : "glassItem"}
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <n.icon size={11} />
                <span>{n.title}</span>
              </button>
            ))}
          </div>
        </aside>
      }
    />
  );
}

function PerforationSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  return (
    <Frame
      sidebar={
        <aside className="sb perforation">
          <div className="perforationRail" />
          <h3>Ticket Lane</h3>
          {NAV.map((n, i) => (
            <button
              key={n.title}
              onClick={() => setActive(n.title)}
              className={active === n.title ? "ticketRow active" : "ticketRow"}
              style={{ animationDelay: `${i * 45}ms` }}
            >
              <span>{n.title}</span>
              <n.icon size={11} />
            </button>
          ))}
          <div className="ticketFoot">{(SUBNAV[active] || []).slice(0, 2).join("  //  ")}</div>
        </aside>
      }
    />
  );
}

function LoomSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  return (
    <Frame
      sidebar={
        <aside className="sb loom">
          <div className="loomHead">
            <Waves size={12} />
            <span>Loom Thread</span>
          </div>
          <div className="loomLine" />
          {NAV.map((n, i) => (
            <button
              key={n.title}
              onClick={() => setActive(n.title)}
              className={active === n.title ? "loomNode active" : "loomNode"}
              style={{ animationDelay: `${i * 38}ms` }}
            >
              <i />
              <n.icon size={11} />
              <span>{n.title}</span>
            </button>
          ))}
        </aside>
      }
    />
  );
}

function BrutFrameSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  return (
    <Frame
      sidebar={
        <aside className="sb brutFrame">
          <div className="brutHead">FRAME CTRL</div>
          {NAV.map((n, i) => (
            <button
              key={n.title}
              onClick={() => setActive(n.title)}
              className={active === n.title ? "brutBlock active" : "brutBlock"}
              style={{ animationDelay: `${i * 35}ms` }}
            >
              <n.icon size={11} />
              <span>{n.title}</span>
            </button>
          ))}
        </aside>
      }
    />
  );
}

function PromptPoetrySidebar() {
  const [active, setActive] = React.useState("Dashboard");
  return (
    <Frame
      sidebar={
        <aside className="sb poetry">
          <div className="poetryHead">
            <Command size={11} />
            <span>prompt.poetry</span>
          </div>
          {NAV.map((n, i) => (
            <button
              key={n.title}
              onClick={() => setActive(n.title)}
              className={active === n.title ? "poetryLine active" : "poetryLine"}
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <i>$</i>
              <b>{n.title.toLowerCase()}</b>
              <em>{active === n.title ? "▌" : ""}</em>
            </button>
          ))}
        </aside>
      }
    />
  );
}

function CathedralSidebar() {
  const [active, setActive] = React.useState("Dashboard");
  return (
    <Frame
      sidebar={
        <aside className="sb cathedral">
          <div className="cathedralHead">
            <CircleDashed size={12} />
            <p>cathedral map</p>
          </div>
          <div className="cathedralVault">
            {NAV.map((n, i) => (
              <button
                key={n.title}
                onClick={() => setActive(n.title)}
                className={active === n.title ? "vaultItem active" : "vaultItem"}
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <n.icon size={11} />
                <span>{n.title}</span>
              </button>
            ))}
          </div>
        </aside>
      }
    />
  );
}

const TABS = [
  { id: "monument", label: "Monument", Component: MonumentSidebar },
  { id: "ribbon", label: "Ribbon Code", Component: RibbonCodeSidebar },
  { id: "orbit", label: "Orbit Slice", Component: OrbitSliceSidebar },
  { id: "swiss", label: "Swiss Grid", Component: SwissGridSidebar },
  { id: "glass", label: "Soft Glass", Component: SoftGlassSidebar },
  { id: "ticket", label: "Perforation", Component: PerforationSidebar },
  { id: "loom", label: "Loom", Component: LoomSidebar },
  { id: "brut", label: "Brut Frame", Component: BrutFrameSidebar },
  { id: "poetry", label: "Prompt Poetry", Component: PromptPoetrySidebar },
  { id: "cathedral", label: "Cathedral", Component: CathedralSidebar },
] as const;

const styles = `
  :root {
    --bg: #eef1ea;
    --panel: #fbfcf8;
    --ink: #131512;
    --muted: #697267;
    --line: #d3d9ce;
  }

  .dark {
    --bg: #0f1310;
    --panel: #131915;
    --ink: #eaf0e8;
    --muted: #8d9a8f;
    --line: #29322a;
  }

  .canva {
    min-height: 100vh;
    padding: 48px 20px 72px;
    display: flex;
    flex-direction: column;
    align-items: center;
    background:
      radial-gradient(circle at 0% -20%, color-mix(in oklab, var(--ink) 10%, transparent), transparent 40%),
      radial-gradient(circle at 100% 10%, color-mix(in oklab, var(--ink) 8%, transparent), transparent 44%),
      var(--bg);
    color: var(--ink);
    font-family: "General Sans", "Satoshi", "IBM Plex Sans", sans-serif;
  }

  .top h1 {
    margin: 0;
    text-align: center;
    font-family: "Canela", "Fraunces", "Iowan Old Style", serif;
    font-size: clamp(34px, 4vw, 52px);
    font-weight: 500;
    letter-spacing: -0.04em;
  }

  .top p {
    margin: 10px 0 0;
    text-align: center;
    color: var(--muted);
    font-size: 14px;
  }

  .tabs {
    margin: 28px 0 34px;
    width: min(980px, 100%);
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 8px;
  }

  .tabs button {
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 9px 11px;
    font-size: 12px;
    letter-spacing: .03em;
    color: var(--muted);
    background: color-mix(in oklab, var(--panel) 85%, transparent);
    cursor: pointer;
    transition: all .2s ease;
  }

  .tabs button.on {
    border-color: var(--ink);
    color: var(--ink);
    background: color-mix(in oklab, var(--ink) 9%, var(--panel));
  }

  .frame {
    width: min(980px, 100%);
    border-radius: 24px;
    overflow: hidden;
    border: 1px solid var(--line);
    background: var(--panel);
    box-shadow: 0 36px 88px -50px rgba(0, 0, 0, 0.48);
  }

  .frameTop {
    height: 38px;
    border-bottom: 1px solid var(--line);
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 14px;
    color: var(--muted);
    font-size: 11px;
    letter-spacing: .09em;
    text-transform: uppercase;
  }

  .frameTop i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: color-mix(in oklab, var(--muted) 60%, transparent);
  }

  .frameTop span { margin-left: 8px; }
  .frameBody { display: flex; }

  .sb {
    width: 310px;
    height: 620px;
    border-right: 1px solid var(--line);
    overflow: hidden;
    position: relative;
    padding: 16px;
  }

  .mainGhost {
    width: calc(100% - 310px);
    min-height: 620px;
    padding: 40px;
    display: grid;
    align-content: center;
    gap: 13px;
  }

  .line {
    height: 11px;
    border-radius: 999px;
    background: color-mix(in oklab, var(--muted) 22%, transparent);
  }

  .line.a { width: 74%; }
  .line.b { width: 91%; }
  .line.c { width: 63%; }
  .line.d { width: 82%; }

  @keyframes cardIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .monument {
    background: linear-gradient(180deg, #f9f8f3, #eff1e8);
    color: #1d201b;
    font-family: "Canela", "Fraunces", serif;
  }

  .monumentHeader {
    display: flex;
    align-items: end;
    justify-content: space-between;
    border-bottom: 1px solid #c9ccbe;
    padding-bottom: 10px;
  }

  .monumentHeader small {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .18em;
  }

  .monumentHeader strong {
    font-size: 46px;
    line-height: 1;
    letter-spacing: -0.03em;
    font-weight: 500;
  }

  .monumentStack {
    margin-top: 10px;
    display: grid;
    gap: 7px;
  }

  .monumentItem {
    border: 1px solid transparent;
    border-radius: 12px;
    background: transparent;
    color: inherit;
    display: grid;
    grid-template-columns: 26px 1fr;
    gap: 8px;
    align-items: center;
    text-align: left;
    padding: 10px 9px;
    cursor: pointer;
    animation: cardIn .38s both;
  }

  .monumentItem i {
    font-style: normal;
    font-size: 11px;
    color: #6a6f5f;
    letter-spacing: .09em;
  }

  .monumentItem span {
    font-size: 19px;
    line-height: 1.1;
  }

  .monumentItem.active {
    border-color: #2a2f25;
    background: #fdfdf9;
  }

  .ribbonCode {
    background: linear-gradient(165deg, #160d11, #260f18);
    color: #f8e8ee;
    padding: 0;
    display: grid;
    grid-template-columns: 56px 1fr;
  }

  .ribbonColumn {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    letter-spacing: .22em;
    font-size: 11px;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    justify-content: center;
    border-right: 1px solid #503141;
    color: #d7afc0;
  }

  .ribbonMain {
    padding: 16px 14px;
    display: grid;
    gap: 7px;
  }

  .ribbonItem {
    border: 1px solid #5f3d4b;
    border-radius: 999px;
    background: #2b1320;
    color: inherit;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 9px 12px;
    text-align: left;
    cursor: pointer;
    animation: cardIn .35s both;
  }

  .ribbonItem.active {
    background: #f8d7e5;
    color: #381426;
    border-color: #f8d7e5;
  }

  .orbitSlice {
    background: radial-gradient(circle at 50% 42%, #ffffff, #eef3ea 60%);
    color: #172219;
  }

  .orbitDial {
    position: absolute;
    width: 220px;
    height: 220px;
    top: 40%;
    left: 50%;
    transition: transform .35s ease;
  }

  .orbitDial div {
    position: absolute;
    inset: 0;
    border: 1px solid #b9c4b7;
    border-radius: 50%;
    clip-path: polygon(50% 50%, 100% 0, 100% 100%);
    transform-origin: center;
  }

  .orbitDial div:nth-child(2) { transform: rotate(90deg); }
  .orbitDial div:nth-child(3) { transform: rotate(180deg); }
  .orbitDial div:nth-child(4) { transform: rotate(270deg); }

  .orbitList {
    position: absolute;
    left: 16px;
    right: 16px;
    bottom: 16px;
    display: grid;
    gap: 6px;
  }

  .orbitRow {
    border: 1px solid #bec9bb;
    border-radius: 999px;
    background: #f8fcf5;
    color: #233026;
    display: flex;
    gap: 7px;
    align-items: center;
    padding: 7px 10px;
    text-align: left;
    cursor: pointer;
    animation: cardIn .35s both;
  }

  .orbitRow.active {
    background: #1f2a20;
    color: #ecf5eb;
    border-color: #1f2a20;
  }

  .swiss {
    background: #f4f4f1;
    color: #161718;
    font-family: "Azeret Mono", "IBM Plex Mono", monospace;
  }

  .swissMark {
    font-size: 11px;
    letter-spacing: .13em;
    margin-bottom: 10px;
    color: #646971;
  }

  .swissMatrix {
    display: grid;
    grid-template-columns: 1fr;
    gap: 7px;
  }

  .swissCell {
    border: 1px solid #cdd1d8;
    border-radius: 0;
    background: #fcfcfb;
    color: inherit;
    padding: 10px 9px;
    display: grid;
    grid-template-columns: 24px 1fr 12px;
    gap: 8px;
    align-items: center;
    text-align: left;
    cursor: pointer;
    box-shadow: 4px 4px 0 0 #e4e7eb;
    animation: cardIn .38s both;
  }

  .swissCell b {
    font-size: 10px;
    color: #5d6470;
  }

  .swissCell.active {
    background: #17191d;
    color: #f0f3f7;
    border-color: #17191d;
    box-shadow: 4px 4px 0 0 #838a98;
  }

  .softGlass {
    background: linear-gradient(170deg, #dce9ef, #f2f6ff 58%);
    color: #17333f;
  }

  .glassAura {
    position: absolute;
    width: 190px;
    height: 190px;
    border-radius: 50%;
    top: -90px;
    right: -56px;
    background: radial-gradient(circle, #ffffffbb, transparent 66%);
    pointer-events: none;
  }

  .glassHead {
    display: flex;
    align-items: center;
    gap: 7px;
    text-transform: uppercase;
    letter-spacing: .12em;
    font-size: 11px;
    color: #3f5d6d;
  }

  .glassInput {
    margin-top: 10px;
    width: 100%;
    border-radius: 999px;
    border: 1px solid #8eb0c2;
    background: #ffffff88;
    padding: 8px 11px;
    color: #17333f;
    font-size: 12px;
    outline: none;
  }

  .glassInput::placeholder { color: #5a7a89; }

  .glassStack {
    margin-top: 10px;
    display: grid;
    gap: 7px;
  }

  .glassItem {
    border: 1px solid #9ebdce;
    border-radius: 14px;
    background: #ffffff5e;
    backdrop-filter: blur(7px);
    -webkit-backdrop-filter: blur(7px);
    color: inherit;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 9px 10px;
    text-align: left;
    cursor: pointer;
    animation: cardIn .38s both;
  }

  .glassItem.active {
    border-color: #17333f;
    box-shadow: inset 0 0 0 1px #17333f;
    background: #eff8ff91;
  }

  .perforation {
    background: #f8efdf;
    color: #2a1d11;
  }

  .perforationRail {
    position: absolute;
    right: 12px;
    top: 12px;
    bottom: 12px;
    width: 12px;
    background-image: radial-gradient(circle, #e3c8aa 40%, transparent 42%);
    background-size: 12px 18px;
    background-repeat: repeat-y;
    opacity: .8;
  }

  .perforation h3 {
    margin: 0 0 10px;
    font-family: "Canela", serif;
    font-size: 31px;
    font-weight: 500;
    letter-spacing: -0.02em;
  }

  .ticketRow {
    position: relative;
    width: calc(100% - 18px);
    border: 1px solid #d7b996;
    border-radius: 10px;
    background: #fff7eb;
    color: inherit;
    padding: 9px 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 7px;
    text-align: left;
    cursor: pointer;
    animation: cardIn .35s both;
  }

  .ticketRow::before,
  .ticketRow::after {
    content: "";
    position: absolute;
    top: 50%;
    width: 10px;
    height: 10px;
    margin-top: -5px;
    border-radius: 50%;
    background: #f8efdf;
  }

  .ticketRow::before { left: -5px; }
  .ticketRow::after { right: -5px; }

  .ticketRow.active {
    background: #2d1f12;
    border-color: #2d1f12;
    color: #f7e9d7;
  }

  .ticketFoot {
    margin-top: 11px;
    font-size: 11px;
    color: #6d5138;
    letter-spacing: .03em;
  }

  .loom {
    background: linear-gradient(180deg, #0f1216, #121b25);
    color: #e8eef6;
    font-family: "Azeret Mono", "IBM Plex Mono", monospace;
  }

  .loomHead {
    display: flex;
    align-items: center;
    gap: 7px;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: .11em;
    color: #95a8c1;
  }

  .loomLine {
    position: absolute;
    left: 25px;
    top: 48px;
    bottom: 16px;
    width: 1px;
    background: linear-gradient(#334357, #5d7da2, #334357);
  }

  .loomNode {
    margin-top: 8px;
    margin-left: 8px;
    width: calc(100% - 8px);
    border: 1px solid #2f3d4f;
    border-radius: 10px;
    background: #182433;
    color: inherit;
    padding: 8px 9px;
    display: grid;
    grid-template-columns: 12px 12px 1fr;
    gap: 8px;
    align-items: center;
    text-align: left;
    cursor: pointer;
    animation: cardIn .35s both;
  }

  .loomNode i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    border: 2px solid #6f8cae;
  }

  .loomNode.active {
    border-color: #8cb6e1;
    background: #22354d;
  }

  .loomNode.active i { background: #8cb6e1; }

  .brutFrame {
    background: #fff3e7;
    color: #17100b;
    font-family: "Azeret Mono", "IBM Plex Mono", monospace;
  }

  .brutHead {
    border: 2px solid #17100b;
    padding: 9px 10px;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: .12em;
    margin-bottom: 8px;
  }

  .brutBlock {
    width: 100%;
    margin-top: 7px;
    border: 2px solid #17100b;
    background: #fff;
    color: inherit;
    padding: 9px 10px;
    display: flex;
    gap: 8px;
    align-items: center;
    text-transform: uppercase;
    font-size: 11px;
    cursor: pointer;
    box-shadow: 4px 4px 0 #17100b;
    animation: cardIn .35s both;
  }

  .brutBlock.active {
    background: #17100b;
    color: #fff3e7;
  }

  .poetry {
    background: #0f1214;
    color: #e6edf1;
    font-family: "IBM Plex Mono", "JetBrains Mono", monospace;
  }

  .poetryHead {
    display: flex;
    align-items: center;
    gap: 7px;
    color: #8d9eac;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .11em;
  }

  .poetryLine {
    width: 100%;
    margin-top: 7px;
    border: 1px solid #2a3238;
    border-radius: 8px;
    background: #14181b;
    color: inherit;
    padding: 8px 9px;
    display: grid;
    grid-template-columns: 10px 1fr 8px;
    gap: 8px;
    align-items: center;
    text-align: left;
    cursor: pointer;
    animation: cardIn .35s both;
  }

  .poetryLine i {
    font-style: normal;
    color: #70be8f;
  }

  .poetryLine b {
    font-weight: 500;
    font-size: 12px;
  }

  .poetryLine em {
    font-style: normal;
    color: #97c4e8;
    animation: blink 1s steps(1) infinite;
  }

  @keyframes blink {
    50% { opacity: 0; }
  }

  .poetryLine.active {
    border-color: #86accf;
    background: #1a2530;
  }

  .cathedral {
    background: radial-gradient(circle at 50% -30%, #f0f5f5, #e9efec 45%, #f4f7f3);
    color: #1e2822;
  }

  .cathedralHead {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-bottom: 10px;
  }

  .cathedralHead p {
    margin: 0;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .13em;
    color: #56675d;
  }

  .cathedralVault {
    position: relative;
    height: 520px;
    border: 1px solid #c4cec5;
    border-radius: 180px 180px 18px 18px;
    padding: 24px 14px 14px;
    background: #fbfdf9;
    display: grid;
    align-content: start;
    gap: 8px;
  }

  .vaultItem {
    border: 1px solid #c3ccc3;
    border-radius: 999px;
    background: #f7fbf4;
    color: inherit;
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 8px 10px;
    text-align: left;
    cursor: pointer;
    animation: cardIn .4s both;
  }

  .vaultItem.active {
    border-color: #263328;
    background: #263328;
    color: #eef6ef;
  }

  @media (max-width: 980px) {
    .tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .frameBody { flex-direction: column; }
    .sb {
      width: 100%;
      height: auto;
      min-height: 340px;
      border-right: 0;
      border-bottom: 1px solid var(--line);
    }
    .mainGhost {
      width: 100%;
      min-height: 260px;
      padding: 26px 20px;
    }
    .orbitDial {
      width: 180px;
      height: 180px;
      top: 44%;
    }
    .cathedralVault { height: auto; }
    .barcodeRow { height: 260px; }
  }
`;

export default function CanvaPage() {
  const { resolvedTheme } = useTheme();
  const [active, setActive] = React.useState<(typeof TABS)[number]["id"]>("monument");
  const current = TABS.find((tab) => tab.id === active) ?? TABS[0];

  return (
    <main className={`canva ${resolvedTheme === "dark" ? "dark" : ""}`}>
      <style>{styles}</style>
      <header className="top">
        <h1>Sidebar Lab / 10 Radical Originals</h1>
        <p>Different form systems, typography systems, border systems, and motion systems.</p>
      </header>

      <nav className="tabs">
        {TABS.map((tab) => (
          <button key={tab.id} className={active === tab.id ? "on" : ""} onClick={() => setActive(tab.id)}>
            {tab.label}
          </button>
        ))}
      </nav>

      <current.Component />
    </main>
  );
}
