"use client";

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "icon";

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-inverse text-inverse-ink hover:bg-neutral-200",
  secondary: "border border-line-strong bg-surface-raised text-ink hover:border-ink-disabled hover:bg-surface-hover",
  ghost: "text-ink-muted hover:bg-surface-hover hover:text-ink",
  danger: "border border-danger/40 bg-danger/10 text-danger hover:border-danger/70 hover:bg-danger/20",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "min-h-9 px-3 type-badge",
  md: "min-h-11 px-5 type-label",
  icon: "h-11 w-11 p-0",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  busy?: boolean;
  icon?: ReactNode;
  responsiveWidth?: boolean;
  size?: ButtonSize;
  variant?: ButtonVariant;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    busy = false,
    children,
    className,
    disabled,
    icon,
    responsiveWidth = false,
    size = "md",
    type = "button",
    variant = "secondary",
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cn(
        "focus-ring duration-fast inline-flex shrink-0 items-center justify-center gap-2 font-medium tracking-widest uppercase transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variantClasses[variant],
        sizeClasses[size],
        responsiveWidth && "w-full sm:w-auto",
        className,
      )}
      {...props}
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> : icon}
      {children}
    </button>
  );
});

export interface IconButtonProps extends Omit<ButtonProps, "aria-label" | "children" | "size"> {
  "aria-label": string;
  icon: ReactNode;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { "aria-label": ariaLabel, title, ...props },
  ref,
) {
  return (
    <Button
      ref={ref}
      size="icon"
      aria-label={ariaLabel}
      title={title ?? ariaLabel}
      {...props}
    />
  );
});
