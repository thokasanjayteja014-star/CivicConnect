// End-to-end test of the citizen-to-authority workflow (spec 10.C S1, S2, S5, S6, S7, S9).
//
// Run ONLY against an isolated test deployment/database (records created here are
// test fixtures). Prerequisites: backend on E2E_API (default :8000) with a bootstrapped
// SYSTEM_ADMIN, frontend on E2E_WEB (default :3000).
//
//   E2E_ADMIN_EMAIL=admin@example.com E2E_ADMIN_PASSWORD=... node tests/e2e/citizen-to-authority.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const { chromium } = createRequire(import.meta.url)("playwright");

const API = process.env.E2E_API || "http://localhost:8000";
const WEB = process.env.E2E_WEB || "http://localhost:3000";
const SHOTS = process.env.E2E_SCREENSHOTS || "";
const run = Date.now().toString(36);
const pwd = "e2e-password-123";

function assert(cond, msg) { if (!cond) throw new Error("ASSERTION FAILED: " + msg); console.log("  ✓ " + msg); }

async function call(method, p, token, body) {
  const r = await fetch(API + p, { method, headers: { "Content-Type": "application/json", ...(token && { Authorization: `Bearer ${token}` }) }, body: body && JSON.stringify(body) });
  const j = r.status === 204 ? null : await r.json();
  if (!r.ok) throw new Error(`${method} ${p} -> ${r.status} ${JSON.stringify(j)}`);
  return j;
}

function png() { // minimal valid 2x2 PNG
  const crcTable = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (b) => { let c = 0xffffffff; for (const x of b) c = crcTable[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (t, d) => { const len = Buffer.alloc(4); len.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(2, 0); ihdr.writeUInt32BE(2, 4); ihdr[8] = 8; ihdr[9] = 2;
  const raw = Buffer.from([0, 128, 128, 128, 128, 128, 128, 0, 128, 128, 128, 128, 128, 128]);
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

async function shot(page, name) { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true }); }

async function login(browser, email, password) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(`${WEB}/login`);
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click("button[type=submit]");
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  return page;
}

(async () => {
  console.log("Setup via admin API (isolated E2E database)");
  const admin = await call("POST", "/api/auth/login", null, { email: process.env.E2E_ADMIN_EMAIL || "admin@example.com", password: process.env.E2E_ADMIN_PASSWORD });
  const at = admin.access_token;
  const dept = await call("POST", "/api/admin/departments", at, { name: `E2E Roads ${run}` });
  await call("POST", "/api/admin/jurisdictions", at, { name: `E2E Zone ${run}`, department_ids: [dept.id],
    boundary: { type: "Polygon", coordinates: [[[60, 5], [100, 5], [100, 35], [60, 35], [60, 5]]] } });
  await call("POST", "/api/admin/responsibilities", at, { department_id: dept.id, category: "ROAD_INFRASTRUCTURE", verified: true });
  const offEmail = `officer-${run}@example.com`, headEmail = `head-${run}@example.com`;
  await call("POST", "/api/admin/users", at, { full_name: "E2E Officer", email: offEmail, password: pwd, role: "OFFICER", department_id: dept.id, designation: "Field officer" });
  await call("POST", "/api/admin/users", at, { full_name: "E2E Head", email: headEmail, password: pwd, role: "DEPARTMENT_ADMIN", department_id: dept.id, designation: "Executive engineer" });

  const browser = await chromium.launch();
  try {
    console.log("S1/S2: citizen registers and reports (AI not configured)");
    const cctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const cp = await cctx.newPage();
    await cp.goto(`${WEB}/register`);
    await cp.fill("#full_name", "Private E2E Citizen");
    await cp.fill("#email", `citizen-${run}@example.com`);
    await cp.fill("#password", pwd);
    await cp.fill("#confirm", pwd);
    await cp.click("button[type=submit]");
    await cp.waitForURL("**/dashboard");
    await cp.getByText("You haven't reported any issues yet").waitFor();
    assert(true, "empty state shown for new citizen");
    await shot(cp, "01-citizen-empty-dashboard");

    await cp.goto(`${WEB}/report`);
    await cp.fill("#desc", "Deep pothole right in front of the bus stop. Two-wheelers swerve into traffic to avoid it.");
    const tmp = path.join(process.env.TMPDIR || "/tmp", `e2e-${run}.png`);
    fs.writeFileSync(tmp, png());
    await cp.setInputFiles("input[type=file]", tmp);
    await cp.getByText("Uploaded and validated").waitFor();
    assert(true, "photo uploaded and validated by backend");
    await shot(cp, "02-report-describe");
    await cp.getByRole("button", { name: "Continue" }).click();
    const map = cp.locator(".leaflet-container");
    await map.waitFor();
    const box = await map.boundingBox();
    await cp.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await cp.getByText("Selected on map").waitFor();
    assert(true, "location picked on map");
    await cp.fill("#landmark", "Opposite city bus stand");
    await shot(cp, "03-report-location");
    await cp.getByRole("button", { name: "Continue" }).click();
    await cp.selectOption("#sev", "SUBSTANTIAL");
    await cp.selectOption("#saf", "SIGNIFICANT");
    await cp.getByRole("button", { name: "Continue to review" }).click();
    await cp.getByRole("button", { name: "Analyze my report" }).click();
    await cp.getByText("AI analysis is not configured on this deployment.").waitFor();
    assert(true, "AI_NOT_CONFIGURED shown; no fabricated analysis");
    await cp.fill("#title", "Deep pothole at bus stand");
    await cp.selectOption("#cat2", "ROAD_INFRASTRUCTURE");
    await cp.getByLabel("I have reviewed these details").check();
    await shot(cp, "04-report-review");
    await cp.getByRole("button", { name: "Submit complaint" }).click();
    await cp.getByText("Complaint submitted").waitFor();
    const ref = (await cp.locator("p.font-mono").first().textContent()).trim();
    assert(/^CVC-\d{8}-[A-Z0-9]{6}$/.test(ref), `reference ID generated (${ref})`);
    assert(await cp.getByText(`Routed to E2E Roads ${run}`).isVisible(), "routed to configured department");
    await shot(cp, "05-report-success");

    console.log("S5: officer processes and resolves");
    const op = await login(browser, offEmail, pwd);
    await op.goto(`${WEB}/authority`);
    await op.getByText(ref).waitFor();
    await shot(op, "06-authority-dashboard");
    await op.locator("tr", { hasText: ref }).getByRole("link", { name: "Open" }).click();
    await op.getByRole("heading", { name: "Deep pothole at bus stand" }).waitFor();
    const apply = async (status, extra) => {
      await op.getByLabel("New status").selectOption(status);
      if (extra) await extra();
      await op.getByRole("button", { name: "Apply" }).click();
      await op.getByText("Status updated.").waitFor();
    };
    await apply("UNDER_REVIEW");
    await op.getByLabel("Officer").selectOption({ label: "E2E Officer — Field officer" });
    await op.getByRole("button", { name: "Assign", exact: true }).click();
    await op.getByText("Officer assigned.").waitFor();
    await apply("IN_PROGRESS", () => op.getByLabel("Citizen-visible remark").fill("Repair crew scheduled"));
    await op.getByLabel("Evidence file").setInputFiles(tmp);
    await op.getByLabel("Evidence description").fill("Pothole filled and compacted");
    await op.getByRole("button", { name: "Upload" }).click();
    await op.getByText("Evidence uploaded.").waitFor();
    await apply("RESOLVED_AWAITING_VERIFICATION");
    assert(await op.getByText("not yet been independently verified").isVisible(), "awaiting verification, not auto-verified");
    await op.getByLabel("Public summary").fill("Pothole reported near a city bus stand");
    await op.getByRole("button", { name: "Approve public display" }).click();
    await op.getByText("Approved for public display.").waitFor();
    assert(await op.getByText("You do not have the VERIFY_RESOLUTION permission").isVisible(), "officer cannot verify");
    await shot(op, "07-authority-review");

    console.log("S6/S9: citizen says not resolved; dept admin rejects, then verifies");
    await cp.goto(`${WEB}/dashboard`);
    await cp.locator("tr", { hasText: ref }).getByRole("link", { name: "Open" }).click();
    await cp.getByText("Repair crew scheduled").waitFor();
    assert(true, "citizen sees citizen-visible remark and timeline");
    await cp.getByLabel("No, it is not resolved").check();
    await cp.fill("#fbr", "The edges are still broken.");
    await cp.getByRole("button", { name: "Submit feedback" }).click();
    await cp.getByText("awaiting review by an authorized reviewer").waitFor();
    assert(true, "reopen request recorded as PENDING; status unchanged");
    await shot(cp, "08-citizen-feedback");

    const hp = await login(browser, headEmail, pwd);
    await hp.goto(`${WEB}/authority/reopen`);
    await hp.getByText("The edges are still broken.").waitFor();
    await hp.getByLabel("Decision reason").fill("Site photo shows the full patch is complete");
    await hp.getByRole("button", { name: "Reject" }).click();
    await hp.getByText("No reopening requests").waitFor();
    assert(true, "dept admin rejected reopening with a reason");
    await hp.goto(`${WEB}/authority`);
    await hp.locator("tr", { hasText: ref }).getByRole("link", { name: "Open" }).click();
    await hp.getByLabel("Verification reason").fill("Reviewed evidence photo and citizen feedback");
    await hp.getByRole("button", { name: "Approve verification" }).click();
    await hp.getByText("Marked verified resolved.").waitFor();
    assert(true, "dept admin verified resolution");
    await shot(hp, "09-verified");

    console.log("S7: public dashboard is privacy-safe and real");
    const pub = await browser.newPage();
    await pub.goto(`${WEB}/public`);
    await pub.getByText("Pothole reported near a city bus stand").waitFor();
    const html = await pub.content();
    assert(!html.includes("Private E2E Citizen") && !html.includes(`citizen-${run}`), "no citizen name/email on public page");
    assert(html.includes("Verified resolved"), "public status distinguishes verified resolution");
    await shot(pub, "10-public");

    const statuses = (await call("GET", `/api/complaints?q=${ref}`, admin.access_token)).items.map((i) => i.status);
    assert(statuses[0] === "VERIFIED_RESOLVED", "final persisted status is VERIFIED_RESOLVED");
    console.log("\nE2E PASSED");
  } finally {
    await browser.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
