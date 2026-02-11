import { ChatIcon, LayersIcon, SparklesIcon } from "../icons";

type AppSidebarProps = {
  isOpen: boolean;
  onToggle: () => void;
  appTitle: string;
  history: string[];
};

const navItems = [
  { label: "Conversations", icon: ChatIcon },
  { label: "Sources", icon: LayersIcon },
  { label: "Prompts", icon: SparklesIcon },
];

export function AppSidebar({ isOpen, onToggle, appTitle, history }: AppSidebarProps) {
  return (
    <aside className={`layout-sidebar ${isOpen ? "open" : "collapsed"}`}>
      <button type="button" className="icon-button sidebar-toggle" onClick={onToggle}>
        {isOpen ? "Hide" : "Show"}
      </button>

      <div className="sidebar-brand">
        <div className="brand-dot" />
        {isOpen ? <span>{appTitle}</span> : <span>A</span>}
      </div>

      <nav className="sidebar-nav" aria-label="Workspace navigation">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.label} type="button" className="sidebar-nav-item">
              <Icon width={16} height={16} />
              {isOpen ? <span>{item.label}</span> : null}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-history">
        {isOpen ? <div className="sidebar-history-title">Recent</div> : null}
        <div className="sidebar-history-list">
          {history.map((item, idx) => (
            <button key={`${idx}-${item}`} type="button" className="sidebar-history-item" title={item}>
              {isOpen ? item : item.slice(0, 1)}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
