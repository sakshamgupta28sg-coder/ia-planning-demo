import Link from "next/link";

const CARDS = [
  {
    href: "/wp",
    title: "Working Plan",
    desc: "Written sales, BOP/EOP inventory, on-order, recommended receipts by week × channel × hierarchy.",
    color: "border-blue-500",
    badge: "WP",
  },
  {
    href: "/skus",
    title: "New SKUs",
    desc: "Add new products into the planning hierarchy with launch weeks, pricing, and cost.",
    color: "border-amber-500",
    badge: "SKU",
  },
];

export default function Home() {
  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-white mb-2">Planning Demo</h1>
        <p className="text-slate-400 text-sm">
          Merchandise planning tool built on Balsam Brands ItemSmart concepts — dummy data.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {CARDS.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className={`block rounded-xl border-l-4 ${c.color} bg-slate-800 p-5 hover:bg-slate-700 transition-colors`}
          >
            <div className="flex items-center gap-3 mb-2">
              <span className="text-xs font-mono font-bold text-slate-400 bg-slate-900 px-2 py-0.5 rounded">
                {c.badge}
              </span>
              <h2 className="font-semibold text-white">{c.title}</h2>
            </div>
            <p className="text-slate-400 text-sm leading-relaxed">{c.desc}</p>
          </Link>
        ))}
      </div>
      <div className="mt-10 text-xs text-slate-600 border-t border-slate-800 pt-4">
        8 product hierarchies · 3 channels · 52 fiscal weeks · dummy data only
      </div>
    </div>
  );
}
