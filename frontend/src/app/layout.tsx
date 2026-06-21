import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Planning Demo",
  description: "Impact Analytics Merchandise Planning — Dummy Data",
};

const NAV = [
  { href: "/", label: "Home" },
  { href: "/wp", label: "Working Plan" },
  { href: "/master", label: "Master SKU" },
  { href: "/placeholders", label: "Placeholders" },
  { href: "/admin", label: "Data Import" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full flex flex-col" style={{ background: "#0b0f1a", color: "#e2e8f0" }}>
        <nav className="flex items-center gap-1 px-6 py-3 border-b border-slate-700 bg-slate-900">
          <span className="font-bold text-blue-400 mr-4 text-sm tracking-widest uppercase">
            Planning
          </span>
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className="px-3 py-1.5 rounded text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <main className="flex-1 p-6">{children}</main>
      </body>
    </html>
  );
}
