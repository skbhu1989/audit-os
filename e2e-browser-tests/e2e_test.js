const chromium = require('@sparticuz/chromium').default;
const puppeteer = require('puppeteer-core');

const BASE = 'http://127.0.0.1:8080';
const results = [];
const consoleErrors = [];

function log(step, ok, detail) {
  results.push({ step, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'} | ${step}${detail ? ' | ' + detail : ''}`);
}

(async () => {
  const browser = await puppeteer.launch({
    args: chromium.args,
    executablePath: await chromium.executablePath(),
    headless: true,
  });
  const page = await browser.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push('PAGE ERROR: ' + err.message));
  page.on('response', (res) => {
    if (res.status() >= 400) consoleErrors.push(`HTTP ${res.status()} - ${res.request().method()} ${res.url()}`);
  });

  const uniqueId = Date.now();
  const email = `browsertest-${uniqueId}@test.example`;

  // ---------- Signup ----------
  await page.goto(`${BASE}/signup`, { waitUntil: 'networkidle0' });
  await page.screenshot({ path: '/tmp/screenshots/01_signup.png' });

  await page.type('input[placeholder="Firm name"]', `Browser Test Firm ${uniqueId}`);
  await page.type('input[placeholder="Your name"]', 'Browser Tester');
  await page.type('input[placeholder="Email"]', email);
  await page.type('input[placeholder="Password"]', 'BrowserTest123!');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 10000 }).catch(() => null),
    page.click('button[type="submit"]'),
  ]);
  await page.screenshot({ path: '/tmp/screenshots/02_after_signup.png' });
  const urlAfterSignup = page.url();
  log('Signup redirects to /engagements', urlAfterSignup.includes('/engagements'), urlAfterSignup);

  // ---------- Create client + engagement via the real UI ----------
  await page.waitForSelector('input[placeholder="Legal name"]', { timeout: 5000 }).catch(() => null);
  const hasClientForm = await page.$('input[placeholder="Legal name"]') !== null;
  log('New-client form renders', hasClientForm);

  if (hasClientForm) {
    await page.type('input[placeholder="Legal name"]', `Browser Test Co ${uniqueId}`);
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/clients') && r.request().method() === 'POST', { timeout: 8000 }).catch(() => null),
      page.click('button:has-text("Create client")').catch(async () => {
        const buttons = await page.$$('button');
        for (const b of buttons) {
          const text = await page.evaluate((el) => el.textContent, b);
          if (text.includes('Create client')) { await b.click(); break; }
        }
      }),
    ]);
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: '/tmp/screenshots/03_after_create_client.png' });
  }

  // Find and fill the new-engagement form that should now be visible
  const fyInput = await page.$('input[placeholder^="FY"]');
  log('New-engagement form appears after client creation', fyInput !== null);
  if (fyInput) {
    await fyInput.type('2025-26');
    const dateInput = await page.$('input[type="date"]');
    if (dateInput) await dateInput.type('03/31/2026');
    const buttons = await page.$$('button');
    for (const b of buttons) {
      const text = await page.evaluate((el) => el.textContent, b);
      if (text.includes('New engagement')) { await b.click(); break; }
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  await page.screenshot({ path: '/tmp/screenshots/04_engagements_list.png' });

  // Click "Open" on whatever engagement now exists
  const openButtons = await page.$$('button');
  let opened = false;
  for (const b of openButtons) {
    const text = await page.evaluate((el) => el.textContent, b);
    if (text.trim() === 'Open') {
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 8000 }).catch(() => null),
        b.click(),
      ]);
      opened = true;
      break;
    }
  }
  log('Opened an engagement into the dashboard', opened);
  await new Promise((r) => setTimeout(r, 1000));
  await page.screenshot({ path: '/tmp/screenshots/05_dashboard.png' });

  const dashboardUrl = page.url();
  log('Landed on /dashboard', dashboardUrl.includes('/dashboard'), dashboardUrl);

  // ---------- Walk through several real pages ----------
  const pagesToVisit = ['/data-centre', '/trial-balance', '/exceptions', '/risk', '/caro'];
  for (const path of pagesToVisit) {
    await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle0', timeout: 8000 }).catch((e) => log(`Navigate to ${path}`, false, e.message));
    await new Promise((r) => setTimeout(r, 500));
    const bodyText = await page.evaluate(() => document.body.innerText);
    const looksBlank = bodyText.trim().length < 10;
    log(`Page ${path} renders content`, !looksBlank, `${bodyText.length} chars of visible text`);
    await page.screenshot({ path: `/tmp/screenshots/06_${path.slice(1)}.png` });
  }

  await browser.close();

  console.log('\n=== Console/JS errors captured during the whole session ===');
  if (consoleErrors.length === 0) {
    console.log('NONE');
  } else {
    consoleErrors.forEach((e) => console.log('  - ' + e));
  }

  console.log('\n=== Summary ===');
  const failed = results.filter((r) => !r.ok);
  console.log(`${results.length - failed.length}/${results.length} checks passed`);
  if (failed.length > 0) {
    console.log('FAILURES:');
    failed.forEach((f) => console.log(`  - ${f.step}: ${f.detail || ''}`));
    process.exit(1);
  }
})().catch((e) => {
  console.error('SCRIPT ERROR:', e);
  process.exit(1);
});
