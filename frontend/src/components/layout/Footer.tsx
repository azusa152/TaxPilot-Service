import { HealthIndicator } from "./HealthIndicator";

export function Footer() {
  return (
    <footer className="border-t px-4 py-3 md:px-6">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          &copy; {new Date().getFullYear()} TaxPilot
        </p>
        <HealthIndicator />
      </div>
    </footer>
  );
}
