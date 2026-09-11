import { cn } from "@/lib/utils";

export function BrandMark({ className, size = 32 }: { className?: string; size?: number }) {
  return (
    <span
      className={cn(
        "relative inline-flex items-center justify-center rounded-[30%] font-bold text-primary-foreground shadow-sm ring-1 ring-inset ring-white/20",
        className,
      )}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.5,
        backgroundImage: "linear-gradient(140deg, var(--primary-hover), var(--primary))",
      }}
    >
      S
    </span>
  );
}

export function BrandLockup({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <BrandMark />
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-tight">SmartSME</div>
        <div className="text-[11px] text-muted-foreground">Business, on autopilot</div>
      </div>
    </div>
  );
}
