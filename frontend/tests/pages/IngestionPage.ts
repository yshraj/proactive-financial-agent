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
  }

  async uploadSampleDocument() {
    await this.page.getByTestId("document-upload-input").setInputFiles({
      name: "sample-client-note.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"),
    });
    await expect(this.page.getByTestId("upload-status")).toBeVisible();
    const row = this.page.getByTestId("upload-status-item").filter({ hasText: "sample-client-note.pdf" });
    await expect(row).toBeVisible();
    // The async pipeline polls job status (~1.2s apart); wait for the
    // terminal state rather than a transient stage message.
    await expect(row).toContainText(/Done|Stored|Merged|Content matches/, { timeout: 15_000 });
  }

  async selectNoteTemplate(templateId: string) {
    await this.page.getByTestId("note-template-select").selectOption(templateId);
    await expect(this.page.getByTestId("note-template-preview")).toBeVisible();
  }

  async ingestTranscript(text: string) {
    await this.page.getByTestId("transcript-input").fill(text);
    await this.page.getByTestId("transcript-submit").click();
  }

  async runComplianceScan(notes: string) {
    await this.page.getByTestId("compliance-scan-input").fill(notes);
    await this.page.getByTestId("compliance-scan-button").click();
    await expect(this.page.getByTestId("compliance-scan-results")).toBeVisible();
  }
}
