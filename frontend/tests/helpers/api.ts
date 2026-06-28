import { expect, type Page, type Response } from "@playwright/test";

export async function waitForSuccessfulApiResponse(
  page: Page,
  urlPart: string,
  action: () => Promise<unknown>
): Promise<Response> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(urlPart) &&
      response.request().method() !== "OPTIONS"
  );

  await action();
  const response = await responsePromise;
  expect(response.ok(), `${urlPart} returned ${response.status()}`).toBeTruthy();
  return response;
}
