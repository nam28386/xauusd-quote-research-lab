import {expect, test} from "@playwright/test";

test("renders verified routes, interactive charts and exact configuration links", async ({page}) => {
  const unexpected: string[] = [];
  page.on("pageerror", error => unexpected.push(error.message));
  page.on("request", request => {
    if (!request.url().startsWith("http://127.0.0.1:8765/")) unexpected.push(request.url());
  });
  await page.goto("/");
  await expect(page.getByRole("heading", {name:"Research observatory",exact:true})).toBeVisible();
  await expect(page.getByText("6,912 result rows")).toBeVisible();
  await expect(page.getByRole("heading", {name:"Sampling under adverse conditions"})).toBeVisible();
  await page.getByLabel("Stress polling interval (ms)").selectOption("500");
  await expect(page.getByRole("row").filter({hasText:"clock-regression"})).toHaveCount(4);
  await page.getByRole("button", {name:/Explore factorial stress/}).click();
  const heat = page.getByRole("img",{name:"Factorial detection heatmap",exact:true});
  await expect(heat.locator(".heatmaplayer image")).toBeVisible();
  await page.getByLabel("Transport delay (ms)").selectOption("100");
  await expect(page.locator("figcaption").getByText(/transport_ms=100/)).toBeVisible();
  const source = await (await page.request.get("/api/v1/table/p21?scenario=isolated&phase_percent=0&transport_ms=100&processing_ms=0")).json();
  const trace = await heat.evaluate(node => {
    const plot = node as HTMLElement & {data: {customdata: number[][]; z: (number|null)[][]}[]};
    return plot.data[0];
  });
  for (const {ordinal, data} of source.rows) {
    const row = trace.customdata.findIndex(values => values.includes(ordinal));
    expect(row).toBeGreaterThanOrEqual(0);
    const column = trace.customdata[row].indexOf(ordinal);
    const wire = data.streams[0].events.recall;
    expect(trace.z[row][column]).toBe(wire === null ? null : Number(wire));
  }
  const image = heat.locator(".heatmaplayer image");
  await expect(image).toBeVisible();
  const rect = await image.boundingBox();
  expect(rect).not.toBeNull();
  await page.mouse.click(rect!.x + rect!.width/8, rect!.y + rect!.height*11/12);
  await expect(page.getByRole("region",{name:"Exact configuration"})).toBeVisible();
  await expect(page.getByText("Truth input SHA-256", {exact:true})).toBeVisible();
  await page.getByText("Verified synthetic input",{exact:true}).click();
  await expect(page.locator(".detail pre").first()).toContainText("SYNTHETIC");

  await page.getByRole("link",{name:"Sampling Sensitivity",exact:false}).click();
  await expect(page.getByRole("img",{name:"Sensitivity curve",exact:true}).locator(".scatterlayer .trace")).not.toHaveCount(0);
  await expect(page.getByRole("img",{name:"Broker as-of sensitivity curve",exact:true}).locator(".scatterlayer .trace")).toHaveCount(2);
  await page.getByLabel("Scenario").selectOption("stable");
  await expect(page.getByText("Unavailable (no_truth_episodes)").first()).toBeVisible();
  const exportHref = await page.getByRole("link",{name:/Export filtered JSON/}).getAttribute("href");
  const response = await page.request.get(exportHref!);
  const body = await response.json();
  expect(body.filters.scenario).toBe("stable");
  expect(body.rows[0].data.streams[0].events.recall).toBeNull();

  await page.getByRole("link",{name:"Tail Decomposition",exact:false}).click();
  await expect(page.getByRole("img",{name:"Tail-decomposition bars"}).locator(".barlayer .trace")).toHaveCount(3);
  await expect(page.getByRole("columnheader",{name:/Cross-estimand/})).toBeVisible();
  await page.getByRole("link",{name:"Identifiability Atlas",exact:false}).click();
  await expect(page.getByRole("heading",{name:"Identical sampled observations"})).toBeVisible();
  await page.getByLabel("Counterexample").selectOption("hidden-2");
  await expect(page.getByText(/History B has 2 episodes and oracle p95 of 0.90/)).toBeVisible();
  await page.getByRole("link",{name:"Evidence & Provenance",exact:false}).click();
  await expect(page.getByRole("heading",{name:"Artifact provenance"})).toBeVisible();
  await page.getByLabel("Evidence version / dataset").selectOption("p2");
  await expect(page.getByLabel("Evidence packet")).toHaveValue("evidence-asynchronous.json");
  await expect(page.getByText("synthetic-source").first()).toBeVisible();
  expect(unexpected).toEqual([]);
});

test("mobile layout keeps navigation and controls usable", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/#factorial");
  await expect(page.getByLabel("Polling interval (ms)")).toBeVisible();
  await expect(page.getByRole("img",{name:"Factorial detection heatmap",exact:true}).locator(".heatmaplayer image")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
