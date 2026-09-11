import { cn } from "@/lib/utils";

/** `contrast` inverts the mark for use on the lime brand panel, where the
 *  default lime-on-lime gradient would disappear. */
type Tone = "brand" | "contrast";

export function BrandMark({
  className,
  size = 32,
  tone = "brand",
}: {
  className?: string;
  size?: number;
  tone?: Tone;
}) {
  const contrast = tone === "contrast";
  return (
    <span
      className={cn(
        "relative inline-flex items-center justify-center rounded-[30%] font-bold shadow-sm ring-1 ring-inset",
        contrast
          ? "bg-[#fbfbf7] text-[#14170a] ring-black/10"
          : "text-primary-foreground ring-white/20",
        className,
      )}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.5,
        backgroundImage: contrast
          ? undefined
          : "linear-gradient(140deg, var(--primary-hover), var(--primary))",
      }}
    >
      S
    </span>
  );
}

export function BrandLockup({ className, tone = "brand" }: { className?: string; tone?: Tone }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <BrandMark tone={tone} />
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-tight">SmartSME</div>
        <div
          className={cn(
            "text-[11px]",
            tone === "contrast" ? "opacity-60" : "text-muted-foreground",
          )}
        >
          Business, on autopilot
        </div>
      </div>
    </div>
  );
}
