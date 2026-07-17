import { ErrorPage } from "../components/ErrorPage";

export default function NotFoundPage() {
  return (
    <ErrorPage
      code="404"
      title="This page doesn't exist"
      description="The link may be out of date, or the page may have moved. Head back to your dashboard to pick up where you left off."
    />
  );
}
