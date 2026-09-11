import { useEffect, useState } from "react";
import { Select } from "./ui/input";
import { api } from "@/lib/api";
import { compactMoney, money } from "@/lib/utils";

interface Point {
  label: string;
  value: number;
  full: string;
}

const RANGES = [
  { label: "Last week", days: 7 },
  { label: "Last month", days: 30 },
  { label: "Last 3 months", days: 90 },
  { label: "Last 6 months", days: 180 },
  { label: "Last year", days: 365 },
];

/** Rounds a max up to a clean axis bound (1, 2, 2.5, 5, 10 x 10^n). */
function niceMax(v: number): number {
  if (v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const f = v / pow;
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return nice * pow;
}

export function RevenueChart({
  currency,
  initialDays = 30,
}: {
  currency: string;
  initialDays?: number;
}) {
  const [days, setDays] = useState(initialDays);
  const [data, setData] = useState<Point[]>([]);
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .get<{ points: Point[] }>(`/reports/revenue?days=${days}`)
      .then((res) => alive && setData(res.points))
      .catch(() => alive && setData([]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [days]);

  const W = 760;
  const H = 260;
  const padL = 60;
  const padR = 18;
  const padT = 16;
  const padB = 34;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const n = data.length;
  const max = niceMax(Math.max(...data.map((d) => d.value), 1));
  const x = (i: number) => (n <= 1 ? padL + plotW / 2 : padL + (i * plotW) / (n - 1));
  const y = (v: number) => padT + plotH - (v / max) * plotH;

  const pts = data.map((d, i) => `${x(i).toFixed(1)},${y(d.value).toFixed(1)}`);
  const linePath = pts.length ? `M ${pts.join(" L ")}` : "";
  const fillPath = linePath
    ? `${linePath} L ${x(n - 1).toFixed(1)},${padT + plotH} L ${x(0).toFixed(1)},${padT + plotH} Z`
    : "";

  const ticks = Array.from({ length: 5 }, (_, i) => (max * i) / 4);
  const labelStep = Math.max(1, Math.ceil(n / 10));
  const total = data.reduce((a, d) => a + d.value, 0);

  function handleMove(e: React.MouseEvent<HTMLDivElement>) {
    if (n === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let idx = 0;
    let best = Infinity;
    for (let i = 0; i < n; i++) {
      const dx = Math.abs(x(i) - px);
      if (dx < best) {
        best = dx;
        idx = i;
      }
    }
    setHover(idx);
  }

  const hoverPt = hover != null ? data[hover] : null;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">
          {loading ? (
            "Loading…"
          ) : (
            <>
              Total <span className="font-semibold text-foreground">{money(total, currency)}</span>
            </>
          )}
        </div>
        <div className="w-44 shrink-0">
          <Select
            value={days}
            onChange={(e) => {
              setDays(Number(e.target.value));
              setHover(null);
            }}
            aria-label="Revenue range"
          >
            {RANGES.map((r) => (
              <option key={r.days} value={r.days}>
                {r.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="relative" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full"
          role="img"
          aria-label="Revenue trend"
        >
          <defs>
            <linearGradient id="rev-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.25" />
              <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Y axis: gridlines + value labels */}
          {ticks.map((tv, i) => {
            const yy = y(tv);
            return (
              <g key={i}>
                <line
                  x1={padL}
                  x2={W - padR}
                  y1={yy}
                  y2={yy}
                  stroke="var(--border)"
                  strokeDasharray="3 4"
                  strokeOpacity="0.7"
                />
                <text
                  x={padL - 10}
                  y={yy + 3}
                  textAnchor="end"
                  className="fill-muted-foreground text-[10px] tabular-nums"
                >
                  {compactMoney(tv, currency)}
                </text>
              </g>
            );
          })}

          <path d={fillPath} fill="url(#rev-fill)" />
          <path
            d={linePath}
            fill="none"
            stroke="var(--chart-1)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* X axis labels, thinned to avoid crowding */}
          {data.map((d, i) =>
            i % labelStep === 0 || i === n - 1 ? (
              <text
                key={i}
                x={x(i)}
                y={H - 8}
                textAnchor="middle"
                className="fill-muted-foreground text-[10px]"
              >
                {d.label}
              </text>
            ) : null,
          )}

          {hover != null && (
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={padT}
              y2={padT + plotH}
              stroke="var(--chart-1)"
              strokeOpacity="0.4"
              strokeWidth="1.5"
            />
          )}

          {data.map((d, i) => (
            <circle
              key={i}
              cx={x(i)}
              cy={y(d.value)}
              r={hover === i ? 5 : 3}
              fill="var(--card)"
              stroke="var(--chart-1)"
              strokeWidth="2"
            />
          ))}
        </svg>

        {hoverPt && hover != null && (
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs shadow-md"
            style={{
              left: `${(x(hover) / W) * 100}%`,
              top: `calc(${(y(hoverPt.value) / H) * 100}% - 10px)`,
            }}
          >
            <div className="font-semibold tabular-nums">{money(hoverPt.value, currency)}</div>
            <div className="text-muted-foreground">{hoverPt.full}</div>
          </div>
        )}
      </div>
    </div>
  );
}
