import { cn } from "@/lib/utils";

export interface BarItem {
  label: string;
  value: number;
  display: string;
}

export function BarList({
  items,
  colorVar = "--chart-1",
  emptyLabel = "No data yet.",
  className,
}: {
  items: BarItem[];
  colorVar?: string;
  emptyLabel?: string;
  className?: string;
}) {
  if (items.length === 0) {
    return (
      <p className={cn("py-6 text-center text-sm text-muted-foreground", className)}>
        {emptyLabel}
      </p>
    );
  }
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className={cn("space-y-2.5", className)}>
      {items.map((it, i) => (
        <li key={i} className="grid grid-cols-[1fr_auto] items-center gap-3">
          <div className="min-w-0">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="truncate text-sm">{it.label}</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(4, (it.value / max) * 100)}%`,
                  backgroundColor: `var(${colorVar})`,
                }}
              />
            </div>
          </div>
          <span className="text-sm font-medium tabular-nums">{it.display}</span>
        </li>
      ))}
    </ul>
  );
}

// A compact vertical bar chart for a time series (e.g. daily revenue).
export function MiniBars({
  data,
  colorVar = "--chart-1",
  className,
  height = 120,
}: {
  data: { label: string; value: number }[];
  colorVar?: string;
  className?: string;
  height?: number;
}) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className={cn("flex items-end gap-1", className)} style={{ height }}>
      {data.map((d, i) => (
        <div
          key={i}
          className="flex flex-1 flex-col items-center justify-end gap-1"
          title={`${d.label}: ${d.value}`}
        >
          <div
            className="w-full rounded-t"
            style={{
              height: `${Math.max(2, (d.value / max) * (height - 18))}px`,
              backgroundColor: `var(${colorVar})`,
              opacity: d.value === 0 ? 0.25 : 1,
            }}
          />
          <span className="text-[9px] text-muted-foreground">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

/** A lightweight, dependency-free revenue chart with a soft gradient fill. */
export function LineChart({
  data,
  colorVar = "--chart-1",
  className,
  height = 200,
}: {
  data: { label: string; value: number }[];
  colorVar?: string;
  className?: string;
  height?: number;
}) {
  const width = 720;
  const top = 18;
  const bottom = 32;
  const chartHeight = height - top - bottom;
  const max = Math.max(...data.map((d) => d.value), 1);
  const x = (i: number) =>
    data.length <= 1 ? width / 2 : 18 + (i * (width - 36)) / (data.length - 1);
  const y = (value: number) => top + chartHeight - (value / max) * chartHeight;
  const points = data.map((d, i) => `${x(i).toFixed(1)},${y(d.value).toFixed(1)}`);
  const linePath = points.length ? `M ${points.join(" L ")}` : "";
  const fillPath = linePath
    ? `${linePath} L ${x(data.length - 1).toFixed(1)},${top + chartHeight} L ${x(0).toFixed(1)},${top + chartHeight} Z`
    : "";
  const gradientId = `line-fill-${colorVar.replace(/[^a-z0-9]/gi, "")}`;

  if (data.length === 0) {
    return (
      <p className={cn("py-10 text-center text-sm text-muted-foreground", className)}>
        No data yet.
      </p>
    );
  }

  return (
    <div className={cn("w-full", className)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="block h-auto w-full overflow-visible"
        role="img"
        aria-label="Revenue trend line chart"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={`var(${colorVar})`} stopOpacity="0.25" />
            <stop offset="100%" stopColor={`var(${colorVar})`} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.33, 0.66, 1].map((ratio) => (
          <line
            key={ratio}
            x1="18"
            x2={width - 18}
            y1={top + chartHeight * ratio}
            y2={top + chartHeight * ratio}
            stroke="var(--border)"
            strokeDasharray="3 4"
            strokeOpacity="0.8"
          />
        ))}
        <path d={fillPath} fill={`url(#${gradientId})`} />
        <path
          d={linePath}
          fill="none"
          stroke={`var(${colorVar})`}
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {data.map((d, i) => (
          <g key={`${d.label}-${i}`}>
            <circle
              cx={x(i)}
              cy={y(d.value)}
              r="3.5"
              fill="var(--card)"
              stroke={`var(${colorVar})`}
              strokeWidth="2"
            />
            <text
              x={x(i)}
              y={height - 6}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px] font-medium"
            >
              {d.label}
            </text>
            <title>{`${d.label}: ${d.value}`}</title>
          </g>
        ))}
      </svg>
    </div>
  );
}
