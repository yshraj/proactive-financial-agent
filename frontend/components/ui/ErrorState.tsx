import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center rounded-xl border border-red-200 bg-red-50/60 px-6 py-10 text-center"
    >
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-red-100 text-red-600">
        <AlertTriangle className="h-5 w-5" aria-hidden />
      </div>
      <h3 className="text-base font-semibold text-red-900">{title}</h3>
      {message && <p className="mt-1 max-w-md text-sm text-red-700">{message}</p>}
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          className="mt-4"
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
