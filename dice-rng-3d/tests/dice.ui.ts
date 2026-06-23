import { expect, test } from "@playwright/test";

test("renders coffee simulator and awards a full pot bonus", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "2D Coffee Simulator" })).toBeVisible();
  await page.getByRole("slider", { name: "water" }).fill("130");
  await page.getByRole("slider", { name: "grounds" }).fill("23");
  await expect(page.getByRole("slider", { name: "water" })).toHaveValue("130");
  await expect(page.getByRole("slider", { name: "grounds" })).toHaveValue("23");

  const canvas = page.locator("canvas");
  await expect(canvas).toBeVisible();

  const nonBackgroundPixels = await canvas.evaluate((element) => {
    const context = (element as HTMLCanvasElement).getContext("webgl2") ?? (element as HTMLCanvasElement).getContext("webgl");
    if (!context) return -1;
    const width = Math.min(140, context.drawingBufferWidth);
    const height = Math.min(140, context.drawingBufferHeight);
    const pixels = new Uint8Array(width * height * 4);
    context.readPixels(0, 0, width, height, context.RGBA, context.UNSIGNED_BYTE, pixels);
    let count = 0;
    for (let index = 0; index < pixels.length; index += 4) {
      const r = pixels[index];
      const g = pixels[index + 1];
      const b = pixels[index + 2];
      if (Math.abs(r - 248) > 12 || Math.abs(g - 251) > 12 || Math.abs(b - 255) > 12) count += 1;
    }
    return count;
  });
  expect(nonBackgroundPixels).toBeGreaterThan(40);

  await page.getByRole("button", { name: "Brew" }).click();
  await page.waitForFunction(() => document.body.textContent?.includes("Full pot bonus earned"), null, { timeout: 16_000 });
  await expect(page.getByText("Full pot bonus earned")).toBeVisible();
  await expect(page.getByText("Round finished")).toBeVisible();
});
