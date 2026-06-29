import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  compact = false,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  compact?: boolean;
}) {
  return (
    <div
      role="alert"
      className={`flex animate-fade-in flex-col items-center justify-center rounded-2xl border border-red-200/80 bg-red-50/50 text-center ${
        compact ? "px-4 py-6" : "px-6 py-10"
      }`}
    >
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-red-100 text-red-600">
        <AlertTriangle className="h-5 w-5" aria-hidden />
      </div>
      <h3 className="text-base font-semibold text-red-950">{title}</h3>
      {message && (
        <p className="mt-2 max-w-md text-sm leading-6 text-red-700/90">{message}</p>
      )}
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          className="mt-5"
          leftIcon={<RefreshCw className="h-4 w-4" aria-hidden />}
          onClick={onRetry}
        >
          Try again
        </Button>
      )}
    </div>
  );
}

export default ErrorState;
