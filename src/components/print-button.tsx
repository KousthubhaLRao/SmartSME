"use client";

import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/icons";

/**
 * Invoices always print on a light background, whatever theme the app is in.
 * Rather than duplicating the whole light palette inside `@media print`, we drop
 * the `.dark` class for the duration of the print and put it straight back, so
 * the printed page is byte-for-byte the light theme. Bound to the browser
 * beforeprint/afterprint events so Ctrl+P behaves the same as the button.
 */
export function PrintButton({ label = "Print" }: { label?: string }) {
  const wasDark = useRef(false);

  useEffect(() => {
    const root = document.documentElement;
    const before = () => {
      wasDark.current = root.classList.contains("dark");
      if (wasDark.current) root.classList.remove("dark");
    };
    const after = () => {
      if (wasDark.current) root.classList.add("dark");
      wasDark.current = false;
    };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
      // Never leave the app stuck in light mode if we unmount mid-print.
      after();
    };
  }, []);

  return (
    <Button variant="outline" size="sm" onClick={() => window.print()}>
      <Icon name="reports" size={16} /> {label}
    </Button>
  );
}
