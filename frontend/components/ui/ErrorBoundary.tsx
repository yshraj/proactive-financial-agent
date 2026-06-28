import React from "react";
import { ErrorState } from "./ErrorState";

interface State {
  hasError: boolean;
  message?: string;
}

/** App-level error boundary so a render error shows a recoverable screen,
 * not a blank page. */
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: unknown): State {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : "Unexpected error",
    };
  }

  componentDidCatch(error: unknown) {
    // Hook point for Sentry/error reporting in production.
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("ErrorBoundary caught:", error);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8">
          <ErrorState
            title="This screen hit an error"
            message={this.state.message}
            onRetry={() => this.setState({ hasError: false })}
          />
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
