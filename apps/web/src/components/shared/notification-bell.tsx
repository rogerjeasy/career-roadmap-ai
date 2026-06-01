"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

export interface NotificationItem {
  id: string;
  title: string;
  body?: string;
  timeLabel: string;
  read?: boolean;
  tone?: "info" | "success" | "warn";
}

export interface NotificationBellProps {
  notifications?: NotificationItem[];
  onMarkAllRead?: () => void;
  className?: string;
}

const TONE_DOT: Record<NonNullable<NotificationItem["tone"]>, string> = {
  info: "bg-green",
  success: "bg-green",
  warn: "bg-terra",
};

function BellIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-4 w-4" aria-hidden="true">
      <path d="M8 2v1M3 12h10l-1-2V7a4 4 0 0 0-8 0v3l-1 2zM6 13a2 2 0 0 0 4 0" />
    </svg>
  );
}

export function NotificationBell({
  notifications = [],
  onMarkAllRead,
  className,
}: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const unread = notifications.filter((n) => !n.read).length;

  return (
    <div className={cn("relative", className)}>
      <button
        type="button"
        title="Notifications"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-[34px] w-[34px] items-center justify-center rounded-[7px] text-ink-2 transition-all duration-[120ms] hover:bg-bg-2 hover:text-ink"
      >
        <BellIcon />
        {unread > 0 && (
          <span className="absolute right-[6px] top-[6px] h-[7px] w-[7px] rounded-full bg-terra ring-2 ring-bg" />
        )}
      </button>

      {open && (
        <>
          {/* Click-away backdrop */}
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 cursor-default"
          />
          <div
            role="menu"
            className="absolute right-0 top-[42px] z-50 w-[320px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-[12px] border border-rule bg-paper shadow-lg ring-1 ring-ink/5"
          >
            <div className="flex items-center justify-between border-b border-rule px-4 py-3">
              <p className="font-serif text-[14px] font-medium text-ink">Notifications</p>
              {unread > 0 && (
                <button
                  type="button"
                  onClick={onMarkAllRead}
                  className="text-[12px] font-medium text-terra transition-colors duration-150 hover:text-terra-2"
                >
                  Mark all read
                </button>
              )}
            </div>

            {notifications.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13px] text-ink-3">
                You&apos;re all caught up.
              </p>
            ) : (
              <ul role="list" className="max-h-[360px] overflow-y-auto">
                {notifications.map((n) => (
                  <li
                    key={n.id}
                    className={cn(
                      "flex gap-2.5 border-b border-rule px-4 py-3 last:border-b-0",
                      !n.read && "bg-bg",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-[5px] h-2 w-2 shrink-0 rounded-full",
                        n.read ? "bg-rule-strong" : TONE_DOT[n.tone ?? "info"],
                      )}
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium leading-snug text-ink">{n.title}</p>
                      {n.body && (
                        <p className="mt-0.5 text-[12px] leading-snug text-ink-3">{n.body}</p>
                      )}
                      <p className="mt-1 text-[11px] text-ink-3">{n.timeLabel}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
