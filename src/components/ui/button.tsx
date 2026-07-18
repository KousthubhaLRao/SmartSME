import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "outline" | "ghost" | "destructive";
type Size = "sm" | "md" | "lg" | "icon";

const variants: Record<Variant, string> = {
  primary:
    "bg-primary text-primary-foreground shadow-[0_6px_16px_-5px_color-mix(in_oklab,var(--primary)_70%,transparent)] hover:bg-primary-hover hover:shadow-md active:shadow-sm",
  secondary:
    "border border-border bg-secondary text-secondary-foreground hover:bg-muted",
  outline:
    "border border-border bg-card text-foreground hover:bg-muted hover:border-foreground/20",
  ghost: "text-foreground hover:bg-muted",
  destructive:
    "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive-hover hover:shadow-md active:shadow-sm",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[0.8125rem]",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-6 text-base",
  icon: "h-9 w-9",
};

export function buttonVariants({
  variant = "primary",
  size = "md",
  className,
}: {
  variant?: Variant;
  size?: Size;
  className?: string;
} = {}): string {
  return cn(
    // Tactile base: smooth multi-property transition, a subtle press on click,
    // and a clear focus ring. No brightness tricks.
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl font-medium select-none",
    "transition-[background-color,border-color,box-shadow,transform,color] duration-150 ease-out",
    "active:translate-y-px focus-visible:focus-ring",
    "disabled:opacity-50 disabled:pointer-events-none disabled:shadow-none",
    variants[variant],
    sizes[size],
    className,
  );
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={buttonVariants({ variant, size, className })} {...props} />
  ),
);
Button.displayName = "Button";
