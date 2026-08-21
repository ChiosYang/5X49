"use client";

import {
  forwardRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cn } from "@/lib/cn";

const controlClass = "focus-ring duration-standard min-h-11 w-full border border-line-strong bg-surface-raised px-4 text-sm text-ink placeholder:text-ink-disabled transition-colors hover:border-ink-disabled disabled:cursor-not-allowed disabled:opacity-50";

export const InputButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement>>(
  function InputButton({ className, type = "button", ...props }, ref) {
    return <button ref={ref} type={type} className={cn(controlClass, className)} {...props} />;
  },
);

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function TextInput({ className, ...props }, ref) {
    return <input ref={ref} className={cn(controlClass, className)} {...props} />;
  },
);

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function TextArea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(controlClass, "resize-none py-3 leading-6", className)}
        {...props}
      />
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...props }, ref) {
    return <select ref={ref} className={cn(controlClass, "px-3", className)} {...props} />;
  },
);

export function FormField({
  children,
  description,
  error,
  label,
}: {
  children: ReactNode;
  description?: ReactNode;
  error?: ReactNode;
  label: ReactNode;
}) {
  return (
    <label className="grid min-w-0 gap-2">
      <span className="type-label text-ink-subtle">{label}</span>
      {description ? <span className="text-xs leading-5 text-ink-disabled">{description}</span> : null}
      {children}
      {error ? <span className="break-words text-xs leading-5 text-danger">{error}</span> : null}
    </label>
  );
}

export function ToggleSwitch({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onChange}
      disabled={disabled}
      className={cn(
        "focus-ring duration-standard relative h-7 w-12 shrink-0 border transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "border-inverse bg-inverse" : "border-line-strong bg-surface-raised",
      )}
    >
      <span
        className={cn(
          "duration-standard absolute top-1 left-1 h-5 w-5 bg-inverse-ink transition-transform",
          checked ? "translate-x-5" : "translate-x-0",
        )}
      />
    </button>
  );
}
