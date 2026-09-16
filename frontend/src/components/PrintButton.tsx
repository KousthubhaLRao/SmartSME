import { Button } from "./ui/button";
import { Icon } from "./Icon";

/**
 * Invoices always print on a light background, whatever theme the app is in.
 *
 * That is arranged entirely in CSS: the dark palette in `index.css` lives
 * inside `@media screen`, so the print stylesheet never sees it and the light
 * values on `:root` are what reaches the printer.
 *
 * This component used to strip the `.dark` class off `<html>` on `beforeprint`
 * and put it back on `afterprint`. It produced the right PDF, but it restyled
 * the live page twice around every print, so the screen visibly flashed to
 * light and back. It also had two sharper edges: the app was briefly in the
 * wrong theme while the print dialog sat open, and if a print was cancelled in
 * a way that never fired `afterprint`, the app stayed light until reload.
 *
 * Doing it in the stylesheet has none of that, and `Ctrl+P` gets the same
 * result as the button without needing a listener at all.
 */
export function PrintButton({ label = "Print" }: { label?: string }) {
  return (
    <Button variant="outline" size="sm" onClick={() => window.print()}>
      <Icon name="reports" size={16} /> {label}
    </Button>
  );
}
