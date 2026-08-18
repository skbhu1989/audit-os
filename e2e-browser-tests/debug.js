const chromium = require('@sparticuz/chromium').default;
const puppeteer = require('puppeteer-core');

const BASE = 'http://127.0.0.1:8080';

(async () => {
  const browser = await puppeteer.launch({
    args: chromium.args,
    executablePath: await chromium.executablePath(),
    headless: true,
  });
  const page = await browser.newPage();
  const consoleMessages = [];
  page.on('console', (msg) => consoleMessages.push(`[${msg.type()}] ${msg.text()}`));
  page.on('pageerror', (err) => consoleMessages.push('PAGE ERROR: ' + err.message + '\n' + err.stack));
  page.on('requestfailed', (req) => consoleMessages.push('REQUEST FAILED: ' + req.url() + ' - ' + req.failure()?.errorText));

  await page.goto(`${BASE}/signup`, { waitUntil: 'load', timeout: 15000 });
  await new Promise((r) => setTimeout(r, 3000)); // generous wait for React to mount

  console.log('=== Console/page/network messages ===');
  consoleMessages.forEach((m) => console.log(m));

  console.log('\n=== document.body.innerHTML (first 2000 chars) ===');
  const html = await page.evaluate(() => document.body.innerHTML);
  console.log(html.slice(0, 2000));

  console.log('\n=== #root element exists? ===');
  const rootExists = await page.evaluate(() => document.getElementById('root') !== null);
  console.log(rootExists);

  console.log('\n=== #root innerHTML length ===');
  const rootHtml = await page.evaluate(() => document.getElementById('root')?.innerHTML.length ?? -1);
  console.log(rootHtml);

  await page.screenshot({ path: '/tmp/screenshots/debug_signup.png' });
  await browser.close();
})().catch((e) => { console.error('SCRIPT ERROR:', e); process.exit(1); });
