import { ErrorPage } from "../components/ErrorPage";

export default function ServerErrorPage() {
  return (
    <ErrorPage
      code="500"
      title="Something went wrong on our side"
      description="The team has been notified. Your data is safe — try reloading, or come back in a moment."
      showRetry
    />
  );
}
