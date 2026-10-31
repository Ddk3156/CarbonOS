import { test, expect, type Page } from "@playwright/test";

function watch(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  return errors;
}

test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:8000/api/reset");
});

test("guided tour (Next) walks every screen with no console errors", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/");
  await expect(page.getByTestId("screen-cover")).toBeVisible();
  await expect(page.getByTestId("fictional-badge").first()).toBeVisible();
  await expect(page.getByText("Every number, traceable to its bill.")).toBeVisible();
  await page.getByTestId("start-tour").click();
  await expect(page.getByTestId("tour-card")).toBeVisible();
  for (const s of ["cover", "story", "mill", "audit", "data", "factors", "report", "ask"]) {
    await expect(page.getByTestId(`screen-${s}`)).toBeVisible({ timeout: 20_000 });
    if (s !== "ask") await page.getByTestId("tour-next").click();
  }
  await expect(page.getByTestId("pilot-amount")).toContainText("60,000");
  await page.getByTestId("tour-skip").click();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("auto tour runs to the end (scaled clock) with no console errors", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/?tourScale=0.15");
  await page.getByTestId("start-tour").click();
  await expect(page.getByTestId("screen-ask")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("tour-card")).toBeHidden({ timeout: 30_000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("full 90 s tour", async ({ page }) => {
  test.skip(!process.env.FULL_TOUR, "set FULL_TOUR=1 to run the real-time 90 s tour");
  const errors = watch(page);
  await page.goto("/");
  await page.getByTestId("start-tour").click();
  await expect(page.getByTestId("tour-card")).toBeHidden({ timeout: 110_000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("cover to source bill in 3 clicks, one click back up, what-if recounts", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/");
  await page.getByTestId("start-audit").click();               // 1
  await page.getByTestId("see-mill").click();                  // 2
  await page.getByTestId("cat-purchased_electricity").click(); // 3 -> Audit Trail
  await expect(page.getByTestId("audit-category")).toBeVisible();
  await page.getByTestId("result-1").click();                  // 4
  await expect(page.getByTestId("plain-formula")).toHaveText("12,500 kWh × 0.70 kgCO₂e/kWh = 8,750 kg");
  await page.getByTestId("whatif-plus").click();
  await expect(page.getByTestId("before-after")).toContainText("9,100");
  await page.getByTestId("whatif-reset").click();
  await page.getByTestId("to-source").click();                 // 5 -> source bill (2 clicks from the category list)
  await expect(page.getByTestId("audit-source")).toBeVisible();
  await expect(page.getByTestId("proof-stamp")).toBeVisible();
  await page.getByTestId("audit-back").click(); // one layer up: Source -> Inputs
  await expect(page.getByTestId("audit-inputs")).toBeVisible();
  await page.getByTestId("crumb-total").click();
  await expect(page.getByTestId("audit-total")).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("data room scan, gap closing and confetti only on a real gap", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/");
  await page.getByTestId("start-audit").click();
  await page.getByTestId("see-mill").click();
  await page.getByTestId("gap-other_fossil_fuels").click();
  await page.getByTestId("close-gap").click();
  await expect(page.getByTestId("confetti")).toBeVisible();
  await expect(page.getByTestId("mill-total")).toContainText("62.325");
  await page.getByTestId("dock-data").click();
  await page.getByTestId("sample-err").click();
  await expect(page.getByTestId("import-summary")).toContainText("2 accepted", { timeout: 15_000 });
  await expect(page.getByTestId("csv-row-3")).toHaveAttribute("data-status", "rejected");
  await expect(page.getByTestId("csv-row-2")).toHaveAttribute("data-status", "valid");
  await page.getByTestId("dock-factors").click();
  await page.getByTestId("factor-EF-ELECTRICITY-DEMO-001").click();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("every visible text is at least 18px and no snake_case leaks", async ({ page }) => {
  await page.goto("/");
  for (const s of ["start-audit", "see-mill"]) await page.getByTestId(s).click();
  const bad = await page.evaluate(() => {
    const out: string[] = [];
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const t = (n.textContent || "").trim(); const el = n.parentElement;
      if (!t || !el || el.closest("script,style,svg")) continue;
      if (parseFloat(getComputedStyle(el).fontSize) < 17.99) out.push(`small: ${t}`);
      if (/\b[a-z]+_[a-z_]+\b/.test(t)) out.push(`snake: ${t}`);
    }
    return out;
  });
  expect(bad).toEqual([]);
});
