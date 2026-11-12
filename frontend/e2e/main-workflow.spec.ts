import { expect, test } from "@playwright/test";

test("main workflow: campaign → discovery → approval → campaign → outreach → export", async ({ page }) => {
  // 1. Open the application (first run creates the administrator).
  await page.goto("/");
  await expect(page.getByText("First run: create the administrator account.")).toBeVisible();
  await page.getByLabel("Your name").fill("Amit");
  await page.getByLabel("Email").fill("amit@e2e.local");
  await page.getByLabel(/^Password/).fill("e2e-test-password");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("No creators yet")).toBeVisible();

  // 2. Create a client and a campaign.
  await page.getByRole("link", { name: "Clients" }).click();
  await page.getByRole("button", { name: "New client" }).first().click();
  await page.getByLabel("Client name").fill("FitLife Guides");
  await page.getByRole("button", { name: "Save client" }).click();
  await expect(page.getByRole("cell", { name: "FitLife Guides" })).toBeVisible();

  await page.getByRole("link", { name: "Campaigns" }).click();
  await page.getByRole("button", { name: "New campaign" }).first().click();
  await page.getByLabel("Campaign name").fill("Fitness guide launch");
  await page.getByLabel("Client").selectOption({ label: "FitLife Guides" });
  await page.getByRole("button", { name: "Save campaign" }).click();
  await expect(page.getByRole("link", { name: "Fitness guide launch" })).toBeVisible();

  // 3-6. Enter niche and filters, run discovery, collect and analyse profiles.
  await page.getByRole("link", { name: "Discover Creators" }).click();
  await page.getByLabel("Niche", { exact: true }).fill("fitness");
  await page.getByLabel("Min followers", { exact: true }).fill("10000");
  await page.getByRole("button", { name: "Run search" }).click();
  await expect(page.getByText("DEMO DATA: these are fictional sample creators")).toBeVisible();
  await expect(page.getByTestId("creator-card")).toHaveCount(6);
  await expect(page.getByRole("tab", { name: "Qualified (2)" })).toBeVisible();
  const rejected = page.getByTestId("creator-card").filter({ hasText: "@demo_fitness_oliver" });
  await expect(rejected.getByText("Selling", { exact: true })).toBeVisible();
  await expect(rejected.getByText("Rejected")).toBeVisible();

  // 7. Approve a lead that needs review.
  const lead = page.getByTestId("creator-card").filter({ hasText: "@demo_fitness_priya" });
  await expect(lead.getByText("Needs review")).toBeVisible();
  await lead.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("@demo_fitness_priya marked Qualified.")).toBeVisible();

  // 8. Add a qualified creator to the campaign.
  const star = page.getByTestId("creator-card").filter({ hasText: "@demo_fitness_aarav" });
  await star.getByRole("button", { name: "Add to campaign" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Campaign").selectOption({ label: "Fitness guide launch (FitLife Guides)" });
  await dialog.getByLabel("Shortlist now (visible to the client)").check();
  await dialog.getByRole("button", { name: "Add to campaign" }).click();
  await expect(page.getByText("1 added.")).toBeVisible();

  // 9. Generate an outreach draft from the creator's page.
  await star.getByRole("link", { name: "@demo_fitness_aarav" }).click();
  await expect(page.getByRole("heading", { name: "@demo_fitness_aarav" })).toBeVisible();
  await expect(page.getByText("This is a fictional DEMO DATA record.")).toBeVisible();
  await expect(page.getByText("Follower fit")).toBeVisible();
  await page.getByRole("button", { name: "Create outreach draft" }).click();
  await page.getByRole("link", { name: "Review it in Outreach" }).click();
  await page.getByRole("button", { name: "Open draft" }).click();
  await expect(page.getByLabel("Message")).toHaveValue(/Hi Aarav,[\s\S]*about fitness[\s\S]*Best,\nAmit/);
  await page.getByRole("button", { name: "Mark as contacted" }).click();
  await expect(page.getByText("Status: Contacted.")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  // The campaign now holds the shortlisted creator.
  await page.getByRole("link", { name: "Campaigns" }).click();
  await page.getByRole("link", { name: "Fitness guide launch" }).click();
  await expect(page.getByRole("link", { name: "@demo_fitness_aarav" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Shortlisted ✓" })).toBeVisible();

  // 10. Export results (CSV from the campaign, Excel from Reports).
  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  const csvFile = await csv;
  expect(csvFile.suggestedFilename()).toBe("creator-finder-campaign.csv");
  const text = (await (await csvFile.createReadStream()).toArray()).join("");
  expect(text).toContain("DEMO DATA");
  expect(text).toContain("demo_fitness_aarav");
  expect(text).toContain("Fitness guide launch");

  await page.getByRole("link", { name: "Reports" }).click();
  const xlsx = page.waitForEvent("download");
  await page.getByRole("listitem").filter({ hasText: "Qualified leads" }).getByRole("button", { name: "Export Excel" }).click();
  expect((await xlsx).suggestedFilename()).toBe("creator-finder-qualified.xlsx");

  // Dashboard and cost page reflect the real records, at zero cost.
  await page.getByRole("link", { name: "Overview" }).click();
  await expect(page.getByText("6 are demo data")).toBeVisible();
  await page.getByRole("link", { name: "Cost & Usage" }).click();
  await expect(page.getByText("the running cost is ₹0")).toBeVisible();
});

test("signed-out visitors cannot read data", async ({ request }) => {
  for (const path of ["/api/creators", "/api/dashboard", "/api/export?scope=all"]) {
    expect((await request.get(path)).status()).toBe(401);
  }
});
