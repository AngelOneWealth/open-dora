"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/users",         label: "Users"         },
  { href: "/teams",         label: "Teams"         },
  { href: "/repos",         label: "Repositories"  },
  { href: "/orgs",          label: "Organisations" },
  { href: "/users/missing", label: "Missing Users" },
];

export default function Navbar() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/users" && pathname.startsWith("/users/missing")) return false;
    if (href === "/users/missing") return pathname.startsWith("/users/missing");
    return pathname === href || (href !== "/" && pathname.startsWith(href + "/") || pathname === href);
  }

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-6xl mx-auto px-6 flex items-center gap-8 h-14">
        {/* Brand */}
        <Link href="/users" className="flex items-center gap-2 shrink-0">
          <span className="text-lg font-bold text-gray-900 tracking-tight">Dora</span>
          <span className="text-xs text-gray-400 font-medium hidden sm:block">DORA metrics</span>
        </Link>

        {/* Divider */}
        <div className="h-5 w-px bg-gray-200 shrink-0" />

        {/* Nav links */}
        <nav className="flex items-center gap-1 overflow-x-auto">
          {NAV_LINKS.map(({ href, label }) => {
            const active = isActive(href);
            return (
              <Link
                key={href}
                href={href}
                className={`px-3 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                  active
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
