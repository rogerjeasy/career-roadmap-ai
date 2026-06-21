"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useAdminUsers } from "@/hooks/use-admin";
import { ROUTES } from "@/lib/constants";
import { formatDate } from "@/lib/date";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { EmptyState } from "@/components/shared/empty-state";
import { RoleBadge, ActiveBadge, FilterSelect } from "@/components/admin/admin-ui";

const PAGE_SIZE = 20;

export default function AdminUsersPage() {
  const router = useRouter();
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("all");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);

  // Debounce the search box so we don't refetch on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Changing a filter always returns to the first page.
  const handleRole = (value: string) => {
    setRole(value);
    setPage(1);
  };
  const handleStatus = (value: string) => {
    setStatus(value);
    setPage(1);
  };

  const { data, isLoading, isError, isFetching } = useAdminUsers({
    page,
    pageSize: PAGE_SIZE,
    search,
    role,
    status,
  });

  const total = data?.total ?? 0;
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="mx-auto max-w-[1100px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Admin"
        title="Users"
        description="Search, filter and manage every account on the platform."
      />

      {/* Filter bar */}
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by email, name or UID…"
            className="w-full rounded-[8px] border border-rule bg-paper py-2 pl-9 pr-3 text-[13.5px] text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 hover:border-rule-strong focus:border-rule-strong"
          />
        </div>
        <div className="flex gap-2">
          <FilterSelect
            value={role}
            onChange={handleRole}
            options={[
              { value: "all", label: "All roles" },
              { value: "user", label: "Users" },
              { value: "admin", label: "Admins" },
              { value: "superadmin", label: "Superadmins" },
            ]}
          />
          <FilterSelect
            value={status}
            onChange={handleStatus}
            options={[
              { value: "all", label: "All status" },
              { value: "active", label: "Active" },
              { value: "inactive", label: "Disabled" },
            ]}
          />
        </div>
      </div>

      {isLoading && <LoadingSpinner fullPage label="Loading users…" />}

      {isError && (
        <EmptyState
          title="Couldn't load users"
          description="The user directory failed to load. Confirm the API is reachable and you still have admin access."
        />
      )}

      {data && data.items.length === 0 && !isLoading && (
        <EmptyState
          title="No users match"
          description="Try clearing the search box or changing the filters."
        />
      )}

      {data && data.items.length > 0 && (
        <>
          {/* Desktop table */}
          <div className="hidden overflow-hidden rounded-[12px] border border-rule bg-paper md:block">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-rule text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Role</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Provider</th>
                  <th className="px-5 py-3">Joined</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {data.items.map((u) => (
                  <tr
                    key={u.uid}
                    onClick={() => router.push(ROUTES.adminUser(u.uid))}
                    className="cursor-pointer transition-colors duration-150 hover:bg-bg-2"
                  >
                    <td className="px-5 py-3">
                      <p className="text-[13.5px] font-medium text-ink">
                        {u.displayName || "—"}
                      </p>
                      <p className="truncate text-[12px] text-ink-3">{u.email}</p>
                    </td>
                    <td className="px-5 py-3">
                      <RoleBadge role={u.role} />
                    </td>
                    <td className="px-5 py-3">
                      <ActiveBadge active={u.isActive} />
                    </td>
                    <td className="px-5 py-3 text-[12.5px] capitalize text-ink-2">
                      {u.provider.replace(".com", "")}
                    </td>
                    <td className="px-5 py-3 text-[12.5px] text-ink-3">
                      {formatDate(u.createdAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <ul className="space-y-2.5 md:hidden">
            {data.items.map((u) => (
              <li key={u.uid}>
                <button
                  type="button"
                  onClick={() => router.push(ROUTES.adminUser(u.uid))}
                  className="flex w-full items-center justify-between gap-3 rounded-[10px] border border-rule bg-paper p-3.5 text-left transition-colors duration-150 hover:border-rule-strong"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[13.5px] font-medium text-ink">
                      {u.displayName || u.email}
                    </p>
                    <p className="truncate text-[12px] text-ink-3">{u.email}</p>
                    <p className="mt-1 text-[11px] text-ink-3">{formatDate(u.createdAt)}</p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <RoleBadge role={u.role} />
                    <ActiveBadge active={u.isActive} />
                  </div>
                </button>
              </li>
            ))}
          </ul>

          {/* Pagination */}
          <div className="mt-5 flex flex-col items-center justify-between gap-3 sm:flex-row">
            <p className="text-[12.5px] text-ink-3">
              Showing <span className="tabular-nums">{from}</span>–
              <span className="tabular-nums">{to}</span> of{" "}
              <span className="tabular-nums">{total}</span>
              {isFetching && <span className="ml-2 text-ink-3/70">updating…</span>}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded-[7px] border border-rule bg-paper px-3.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-[12.5px] tabular-nums text-ink-3">Page {page}</span>
              <button
                type="button"
                onClick={() => setPage((p) => p + 1)}
                disabled={!data.hasNext}
                className="rounded-[7px] border border-rule bg-paper px-3.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
