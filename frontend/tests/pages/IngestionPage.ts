import { expect, type Page } from "@playwright/test";

export class IngestionPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/admin");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "Ingestion" })).toBeVisible();
    await expect(this.page.getByTestId("document-dropzone")).toBeVisible();
    await expect(this.page.getByTestId("stored-documents")).toBeVisible();
    await this.readyForUpload();
  }

  /**
   * Wait until uploads can actually be processed. The cost hint renders only
   * after React has hydrated AND the credit summary query resolved — before
   * that, a file-input change event is either lost (no listener yet) or
   * hard-stopped by the credits gate, so tests that upload straight after
   * goto() flake on slower engines (firefox, emulated tablet) under CI load.
   */
  async readyForUpload() {
    await expect(this.page.getByTestId("credit-cost-document_upload")).toBeVisible();
  }

  async uploadSampleDocument() {
    await this.readyForUpload();
    await this.page.getByTestId("document-upload-input").setInputFiles({
      name: "sample-client-note.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"),
    });
    await expect(this.page.getByTestId("upload-status")).toBeVisible();
    const row = this.page.getByTestId("upload-status-item").filter({ hasText: "sample-client-note.pdf" });
    await expect(row).toBeVisible();
    // The async pipeline polls job status (~1.5s apart); wait for the
    // terminal state rather than a transient stage message.
    await expect(row).toContainText(/Done|Stored|Merged|Content matches/, { timeout: 15_000 });
  }

  async ingestTranscript(text: string) {
    await this.page.getByTestId("transcript-input").fill(text);
    await this.page.getByTestId("transcript-submit").click();
  }
}
