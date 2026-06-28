import { expect, test as base } from "@playwright/test";
import { collectConsoleErrors } from "../helpers/console";
import { AiCopilotPage } from "../pages/AiCopilotPage";
import { AppShell } from "../pages/AppShell";
import { DashboardPage } from "../pages/DashboardPage";
import { IngestionPage } from "../pages/IngestionPage";
import { LandingPage } from "../pages/LandingPage";
import { LoginPage } from "../pages/LoginPage";
import { MeetingBriefPage } from "../pages/MeetingBriefPage";
import { SettingsPage } from "../pages/SettingsPage";

type AppFixtures = {
  app: {
    aiCopilot: AiCopilotPage;
    dashboard: DashboardPage;
    ingestion: IngestionPage;
    landing: LandingPage;
    login: LoginPage;
    meetingBrief: MeetingBriefPage;
    settings: SettingsPage;
    shell: AppShell;
  };
};

export const test = base.extend<AppFixtures>({
  page: async ({ page }, use) => {
    const consoleErrors = collectConsoleErrors(page);
    await use(page);
    expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
  },

  app: async ({ page }, use) => {
    await use({
      aiCopilot: new AiCopilotPage(page),
      dashboard: new DashboardPage(page),
      ingestion: new IngestionPage(page),
      landing: new LandingPage(page),
      login: new LoginPage(page),
      meetingBrief: new MeetingBriefPage(page),
      settings: new SettingsPage(page),
      shell: new AppShell(page),
    });
  },
});

export { expect } from "@playwright/test";
