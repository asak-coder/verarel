"use client";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(124,58,237,0.18),_transparent_28%),linear-gradient(180deg,_#050816_0%,_#0b1120_42%,_#111827_100%)] text-white">
      <section className="mx-auto flex max-w-7xl flex-col gap-8 px-4 py-6 md:px-8">
        <header className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20 backdrop-blur">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-violet-300/80">verarel.com</p>
              <h1 className="mt-2 text-3xl font-black md:text-5xl">Dating intelligence, cached and fast.</h1>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm md:text-base">
              <Metric label="API target" value="under 300ms cached" />
              <Metric label="Security" value="JWT + rate limits" />
            </div>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-white/70 md:text-base">
            Compatibility, smart replies, trust scoring, and safe date planning in one production-ready platform.
          </p>
        </header>

        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="Compatibility engine" subtitle="Cached match score with explainable reasons">
            <ScoreRing score={86} />
            <div className="space-y-3">
              <ReasonChip text="Shared interests in coffee and travel" />
              <ReasonChip text="Similar communication style" />
              <ReasonChip text="Close enough to meet" />
            </div>
          </Panel>

          <Panel title="Trust score + verification" subtitle="User safety, verification, and abuse signals">
            <div className="flex items-end gap-4">
              <ScoreRing score={72} accent="emerald" />
              <div className="space-y-2 text-sm text-white/80">
                <StatLine label="Tier" value="High" />
                <StatLine label="Verified" value="Yes" />
                <StatLine label="Cached" value="Yes" />
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <StatCard label="Reports" value="1" />
              <StatCard label="Blocks" value="0" />
            </div>
            <button className="mt-4 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-3 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-400/15">
              Generate selfie verification upload
            </button>
          </Panel>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <Panel title="Smart conversation assistant" subtitle="Reply suggestions above the input bar">
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <button className="rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12">
                  What are you into lately?
                </button>
                <button className="rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12">
                  Want to grab coffee this week?
                </button>
                <button className="rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm text-white transition hover:bg-white/12">
                  That sounds fun—tell me more.
                </button>
              </div>
              <textarea
                placeholder="Write a message..."
                className="min-h-28 w-full rounded-2xl border border-white/10 bg-black/20 p-4 text-sm outline-none placeholder:text-white/40 focus:border-violet-400/60"
              />
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-white/45">Autofill ready</span>
                <div className="flex gap-2">
                  <button className="rounded-xl bg-violet-500 px-4 py-2 text-sm font-semibold text-white">Send</button>
                  <button className="rounded-xl border border-white/10 px-4 py-2 text-sm font-semibold text-white/80">
                    Tone check
                  </button>
                </div>
              </div>
            </div>
          </Panel>

          <Panel title="Fraud detection" subtitle="Risk flags from swipe and messaging behaviour">
            <div className="space-y-4">
              <RiskRow label="Same IP multi-account" value="monitor" tone="amber" />
              <RiskRow label="High swipe rate" value="flag" tone="rose" />
              <RiskRow label="Repeated messages" value="flag" tone="rose" />
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-sm font-medium text-white">Risk score</p>
                <div className="mt-3 h-3 rounded-full bg-white/10">
                  <div className="h-3 w-1/3 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-rose-500" />
                </div>
                <p className="mt-2 text-xs text-white/50">Escalate above threshold and cache decision in Redis.</p>
              </div>
            </div>
          </Panel>
        </div>

        <Panel title="Smart date planner" subtitle="PostGIS midpoint + venue suggestions">
          <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <p className="text-sm text-white/50">Midpoint</p>
                <p className="mt-1 text-lg font-semibold">12.9721, 77.5938</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <VenueCard name="Harbor Light Cafe" rating={4.9} venueType="cafe" address="120 Market Street" />
                <VenueCard name="Central Garden Park" rating={4.8} venueType="park" address="8 Garden Lane" />
                <VenueCard name="Blue Hour Bistro" rating={4.7} venueType="restaurant" address="44 Riverfront Drive" />
              </div>
            </div>

            <div className="overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-violet-500/15 to-cyan-400/10 p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-white/60">Map preview</p>
                <span className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs">Leaflet-ready</span>
              </div>
              <div className="mt-4 grid min-h-80 place-items-center rounded-2xl border border-white/10 bg-[#08111f]">
                <div className="text-center">
                  <p className="text-lg font-semibold">Venue markers</p>
                  <p className="mt-2 max-w-sm text-sm text-white/60">
                    Replace this stub with a Leaflet map in production and hide exact user locations.
                  </p>
                  <div className="mt-4 flex flex-wrap justify-center gap-2">
                    <span className="rounded-full bg-white/10 px-3 py-1 text-xs">Harbor Light Cafe</span>
                    <span className="rounded-full bg-white/10 px-3 py-1 text-xs">Central Garden Park</span>
                    <span className="rounded-full bg-white/10 px-3 py-1 text-xs">Blue Hour Bistro</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Panel>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.2em] text-white/45">{label}</p>
      <p className="mt-1 text-sm font-semibold">{value}</p>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-xl shadow-black/10 backdrop-blur">
      <div className="mb-5">
        <h2 className="text-xl font-bold">{title}</h2>
        <p className="mt-1 text-sm text-white/55">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

function ScoreRing({ score, accent = "violet" }: { score: number; accent?: "violet" | "emerald" }) {
  const colorClass = accent === "emerald" ? "from-emerald-400 to-cyan-400" : "from-violet-400 to-fuchsia-400";
  return (
    <div className="relative flex h-36 w-36 items-center justify-center rounded-full bg-white/5">
      <div className={`absolute inset-3 rounded-full bg-gradient-to-br ${colorClass} opacity-80 blur-xl`} />
      <div className="relative flex h-28 w-28 items-center justify-center rounded-full border border-white/10 bg-[#0b1120]">
        <span className="text-3xl font-black">{score}</span>
        <span className="absolute bottom-4 text-[11px] uppercase tracking-[0.2em] text-white/45">/ 100</span>
      </div>
    </div>
  );
}

function ReasonChip({ text }: { text: string }) {
  return <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white/85">{text}</div>;
}

function StatLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-white/50">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
      <p className="text-xs uppercase tracking-[0.2em] text-white/45">{label}</p>
      <p className="mt-2 text-2xl font-black">{value}</p>
    </div>
  );
}

function RiskRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "amber" | "rose";
}) {
  const toneClass =
    tone === "amber"
      ? "text-amber-300 border-amber-400/20 bg-amber-400/10"
      : "text-rose-300 border-rose-400/20 bg-rose-400/10";
  return (
    <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 p-4">
      <span className="text-sm font-medium">{label}</span>
      <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.15em] ${toneClass}`}>{value}</span>
    </div>
  );
}

function VenueCard({
  name,
  rating,
  venueType,
  address,
}: {
  name: string;
  rating: number;
  venueType: string;
  address: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="font-semibold">{name}</p>
      <p className="mt-1 text-sm text-white/55">
        {rating.toFixed(1)}★ · {venueType}
      </p>
      <p className="mt-2 text-xs text-white/45">{address}</p>
    </div>
  );
}
