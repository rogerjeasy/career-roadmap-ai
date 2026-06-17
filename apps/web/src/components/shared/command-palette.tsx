"use client";

import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { ROUTES } from "@/lib/constants";
import { useUIStore } from "@/store/ui.store";
import { cn } from "@/lib/utils";

interface CommandItem {
  id: string;
  label: string;
  group: "Pages" | "Actions";
  keywords: string;
  href: string;
}

// Navigation + quick actions — every entry routes to a real, implemented page.
const COMMANDS: CommandItem[] = [
  { id: "today", label: "Today", group: "Pages", keywords: "dashboard home overview", href: ROUTES.dashboard },
  { id: "roadmap", label: "Roadmap", group: "Pages", keywords: "plan phases milestones", href: ROUTES.roadmap },
  { id: "skill-graph", label: "Skill Graph", group: "Pages", keywords: "skills map gaps", href: ROUTES.skillGraph },
  { id: "coach", label: "AI Coach", group: "Pages", keywords: "chat twin assistant", href: ROUTES.coach },
  { id: "market", label: "Market Pulse", group: "Pages", keywords: "salary trends demand intelligence", href: ROUTES.market },
  { id: "opportunities", label: "Opportunities", group: "Pages", keywords: "jobs matches radar roles", href: ROUTES.opportunities },
  { id: "newsletter", label: "Newsletter", group: "Pages", keywords: "digest email subscribe", href: ROUTES.newsletter },
  { id: "cv", label: "CV & Profile", group: "Pages", keywords: "resume analysis upload", href: ROUTES.cvAnalysis },
  { id: "evidence", label: "Evidence Vault", group: "Pages", keywords: "achievements proof certifications", href: ROUTES.evidence },
  { id: "portfolio", label: "Portfolio", group: "Pages", keywords: "projects work showcase", href: ROUTES.portfolio },
  { id: "network", label: "Network", group: "Pages", keywords: "contacts people outreach events", href: ROUTES.networking },
  { id: "progress", label: "Progress", group: "Pages", keywords: "review health streak", href: ROUTES.progress },
  { id: "schedule", label: "Schedule", group: "Pages", keywords: "calendar blocks habits time", href: ROUTES.schedule },
  { id: "books", label: "Books", group: "Pages", keywords: "reading list", href: ROUTES.books },
  { id: "monthly-plan", label: "Monthly Plan", group: "Pages", keywords: "month goals", href: ROUTES.monthlyPlan },
  { id: "settings", label: "Settings", group: "Pages", keywords: "preferences account notifications", href: ROUTES.settings },
  { id: "help", label: "Help & feedback", group: "Pages", keywords: "support contact bug idea", href: ROUTES.help },
  // Actions
  { id: "generate", label: "Generate a roadmap", group: "Actions", keywords: "new create plan onboarding", href: ROUTES.roadmapGenerate },
  { id: "log-activity", label: "Log activity", group: "Actions", keywords: "time hours track deep work", href: ROUTES.schedule },
  { id: "edit-profile", label: "Edit profile", group: "Actions", keywords: "name role target", href: ROUTES.settingsProfile },
  { id: "integrations", label: "Connect an integration", group: "Actions", keywords: "github linkedin calendar oauth", href: ROUTES.settingsIntegrations },
];

function matches(item: CommandItem, q: string): boolean {
  if (!q) return true;
  const haystack = `${item.label} ${item.keywords} ${item.group}`.toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => haystack.includes(term));
}

interface CommandPaletteBodyProps {
  onSelect: (href: string) => void;
}

function CommandPaletteBody({ onSelect }: CommandPaletteBodyProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const results = useMemo(() => COMMANDS.filter((c) => matches(c, query)), [query]);
  const active = Math.min(activeIndex, Math.max(0, results.length - 1));

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(results.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = results[active];
      if (item) onSelect(item.href);
    }
  };

  return (
    <div className="flex flex-col">
      <input
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActiveIndex(0);
        }}
        onKeyDown={onKeyDown}
        placeholder="Search pages and actions…"
        autoFocus
        aria-label="Search pages and actions"
        className="w-full border-b border-rule bg-transparent px-4 py-3.5 text-[14px] text-ink placeholder:text-ink-3 focus:outline-none"
      />

      <ul className="max-h-[340px] overflow-y-auto py-2" role="listbox">
        {results.length === 0 ? (
          <li className="px-4 py-6 text-center text-[13px] text-ink-3">
            No matches for &ldquo;{query}&rdquo;
          </li>
        ) : (
          results.map((item, i) => {
            const isActive = i === active;
            const showGroup = i === 0 || results[i - 1].group !== item.group;
            return (
              <li key={item.id} role="option" aria-selected={isActive}>
                {showGroup && (
                  <p className="px-4 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                    {item.group}
                  </p>
                )}
                <button
                  type="button"
                  onMouseMove={() => setActiveIndex(i)}
                  onClick={() => onSelect(item.href)}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-[13.5px] transition-colors duration-100",
                    isActive ? "bg-bg-2 text-ink" : "text-ink-2",
                  )}
                >
                  <span className="min-w-0 truncate font-medium">{item.label}</span>
                  <span className="shrink-0 text-[11px] text-ink-3">{item.href}</span>
                </button>
              </li>
            );
          })
        )}
      </ul>

      <div className="flex items-center gap-3 border-t border-rule px-4 py-2.5 text-[11px] text-ink-3">
        <span>↑↓ to navigate</span>
        <span>↵ to open</span>
        <span>esc to close</span>
      </div>
    </div>
  );
}

/**
 * Global command palette (⌘K / Ctrl+K). Mounted once in the app shell so the
 * keyboard shortcut works on every authenticated page. Open state lives in the
 * UI store, so the sidebar and topbar search affordances open it too.
 */
export function CommandPalette() {
  const router = useRouter();
  const open = useUIStore((s) => s.commandOpen);
  const setOpen = useUIStore((s) => s.setCommandOpen);
  const toggle = useUIStore((s) => s.toggleCommand);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  const handleSelect = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        showCloseButton={false}
        className="top-[12%] max-w-xl translate-y-0 gap-0 overflow-hidden p-0"
      >
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <CommandPaletteBody onSelect={handleSelect} />
      </DialogContent>
    </Dialog>
  );
}
