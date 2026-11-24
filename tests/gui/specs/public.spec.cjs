const { test, expect, open, assertLayout, checkA11y } = require('../support.cjs');

test.use({ role: 'guest' });

const emblem = page => page.getByRole('button', { name: '上海交通大学校徽', exact: true });
const trialDialog = page => page.getByRole('dialog', { name: '试验账号登录', exact: true });

async function openTrial(page) {
  await open(page, '/auth?lang=zh');
  await emblem(page).click();
  const dialog = trialDialog(page);
  await expect(dialog).toBeVisible();
  return dialog;
}

test('[live-read] public sign-in presents the campus identity entry and site information', async ({ page }) => {
  await open(page, '/auth?lang=zh');
  await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toHaveAttribute('href', '/api/auth/jaccount');
  await expect(page.getByText('试点验证版 V0.9', { exact: true })).toBeVisible();
  await expect(page.getByRole('contentinfo', { name: '网站备案信息' })).toContainText('沪交ICP备20260352');
  await expect(page.getByRole('group', { name: 'Language / 语言' })).toBeVisible();
  await expect(emblem(page)).toBeVisible();
  await expect(page.getByRole('textbox')).toHaveCount(0);
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('[live-read] switching public sign-in to English persists on reload', async ({ page }) => {
  await open(page, '/auth?lang=zh');
  await page.getByRole('button', { name: 'EN', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Sign in with jAccount', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'EN', exact: true })).toHaveAttribute('aria-pressed', 'true');
  // Remove the explicit Chinese URL override before checking the saved preference.
  await open(page, '/auth');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('link', { name: 'Sign in with jAccount', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '中文', exact: true }).click();
  await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toBeVisible();
});

test('[live-read] known jAccount error query states remain readable and retryable', async ({ page }) => {
  const errors = {
    state: 'jAccount 登录已过期，请重新登录。',
    provider: 'jAccount 登录暂未完成，请重试。',
    denied: '已取消 jAccount 登录，可重新登录。',
    unavailable: 'jAccount 登录暂不可用，请稍后重试或联系系统管理员。',
    forbidden_role: '此账号无法通过 jAccount 登录，请联系系统管理员。',
  };
  for (const [code, message] of Object.entries(errors)) {
    // These are presentation query parameters, not real OAuth callback attempts.
    await open(page, `/auth?lang=zh&jaccount_error=${code}`);
    await expect(page.getByRole('alert')).toHaveText(message);
    await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toHaveAttribute('href', '/api/auth/jaccount');
  }
});

test('[live-read] unknown jAccount error values do not render arbitrary messages', async ({ page }) => {
  await open(page, '/auth?lang=zh&jaccount_error=unexpected');
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toBeVisible();
});

test('[live-read] hostile-looking error queries are blocked by the WAF or safely ignored', async ({ page }, info) => {
  const evidence = [], dialogs = [];
  page.on('dialog', async dialog => { dialogs.push({ type: dialog.type(), message: dialog.message() }); await dialog.dismiss(); });
  try {
    for (const code of ['__proto__', 'constructor', '<script>window.GUI_AUDIT_PROBE=1</script>']) {
      const path = `/auth?lang=zh&jaccount_error=${encodeURIComponent(code)}`;
      const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
      expect(response, 'A document response must be available for the security boundary evidence').not.toBeNull();
      const chain = [];
      for (let request = response.request(); request; request = request.redirectedFrom()) {
        const received = await request.response();
        chain.unshift({ url: request.url(), method: request.method(), status: received ? received.status() : null });
      }
      const record = { input: code, requested_url: new URL(path, page.url()).href, final_url: page.url(), status: response.status(), redirects: chain };
      evidence.push(record);
      const wafBlocked = [200, 403].includes(response.status()) && await page.getByText('访问禁止', { exact: true }).isVisible();
      if (wafBlocked) {
        await expect(page.locator('body')).toContainText('检测到可疑访问');
        record.boundary = 'WAF denied the document before the application rendered';
        info.annotations.push({ type: 'security-boundary', description: `HTTP ${response.status()} WAF blocked ${record.requested_url}; application fallback for this value was not reached.` });
      } else {
        await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toBeVisible();
        await expect(page.getByRole('alert')).toHaveCount(0);
        record.boundary = 'Application safely ignored an unrecognized error value';
      }
      await expect(page.locator('script').filter({ hasText: 'GUI_AUDIT_PROBE' })).toHaveCount(0);
      expect(await page.evaluate(() => window.GUI_AUDIT_PROBE), 'Query text must never execute as JavaScript').toBeUndefined();
      expect(dialogs, 'Query text must not open a JavaScript dialog').toEqual([]);
    }
  } finally {
    await info.attach('security-response-boundaries.json', { body: Buffer.from(JSON.stringify(evidence, null, 2)), contentType: 'application/json' });
  }
});

test('[live-read] a safe saved-report return URL is preserved in the jAccount entry', async ({ page }) => {
  const target = '/reports/pdf/gui-readonly-return?lang=en';
  await open(page, `/auth?lang=en&return_to=${encodeURIComponent(target)}`);
  await expect(page.getByRole('link', { name: 'Sign in with jAccount', exact: true })).toHaveAttribute('href', `/api/auth/jaccount?return_to=${encodeURIComponent(target)}`);
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
});

test('[live-read] unsafe duplicate and looping return URLs are discarded', async ({ page }) => {
  const values = ['https://example.invalid/escape', '//example.invalid/escape', '/auth', '/admin/reports', '/reports/pdf/valid?lang=en&extra=1'];
  for (const target of values) {
    await open(page, `/auth?lang=zh&return_to=${encodeURIComponent(target)}`);
    await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toHaveAttribute('href', '/api/auth/jaccount');
  }
  await open(page, '/auth?lang=zh&return_to=%2Freports%2Fpdf%2Fone&return_to=%2Freports%2Fpdf%2Ftwo');
  await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toHaveAttribute('href', '/api/auth/jaccount');
});

test('[live-read] guest workspace and administrator routes enforce their login gates', async ({ page }) => {
  for (const path of ['/paper-upload', '/reports']) {
    await open(page, path);
    await expect(page).toHaveURL(/\/auth$/);
    await expect(page.getByRole('link', { name: /jAccount/ })).toBeVisible();
    await expect(page.getByRole('table')).toHaveCount(0);
  }
  await open(page, '/reports/pdf/gui-readonly-return?lang=en');
  await expect(page).toHaveURL(/\/auth\?/);
  await expect(page.getByRole('link', { name: /jAccount/ })).toHaveAttribute('href', `/api/auth/jaccount?return_to=${encodeURIComponent('/reports/pdf/gui-readonly-return?lang=en')}`);
  for (const path of ['/admin/reports', '/admin/feedback', '/admin/reports/gui-readonly-return']) {
    await open(page, path);
    await expect(page).toHaveURL(/\/admin\/login$/);
    await expect(page.getByRole('heading', { name: '管理员登录', exact: true })).toBeVisible();
    await expect(page.getByRole('table')).toHaveCount(0);
  }
});

test('[live-read] trial entry supports keyboard focus Escape and credential clearing', async ({ page }) => {
  await open(page, '/auth?lang=zh');
  const trigger = emblem(page);
  await trigger.focus();
  await page.keyboard.press('Enter');
  const dialog = trialDialog(page);
  await expect(dialog).toBeVisible();
  const account = dialog.getByLabel('账号', { exact: true });
  const password = dialog.getByLabel('密码', { exact: true });
  await expect(account).toBeFocused();
  await account.fill('GUI-never-submitted');
  await password.fill('GUI-ephemeral-secret-never-submitted');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(trialDialog(page).getByLabel('账号', { exact: true })).toHaveValue('');
  await expect(trialDialog(page).getByLabel('密码', { exact: true })).toHaveValue('');
});

test('[injected] trial login error clears and refocuses password without a live credential attempt', async ({ page }) => {
  const requests = [];
  await page.route('**/api/auth/trial-login', async route => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ status: 401, json: { message: '账号或密码错误，请重试。' } });
  });
  const dialog = await openTrial(page);
  await dialog.getByLabel('账号', { exact: true }).fill('  GUI-injected-account  ');
  await dialog.getByLabel('密码', { exact: true }).fill('GUI-injected-not-live');
  await dialog.getByRole('button', { name: '登录', exact: true }).click();
  await expect(dialog.getByRole('alert')).toHaveText('账号或密码错误，请重试。');
  await expect(dialog.getByLabel('密码', { exact: true })).toHaveValue('');
  await expect(dialog.getByLabel('密码', { exact: true })).toBeFocused();
  await expect(dialog.getByLabel('密码', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  expect(requests).toEqual([{ username: 'GUI-injected-account', password: 'GUI-injected-not-live' }]);
  await expect(page).toHaveURL(/\/auth\?lang=zh$/);
});

test('[injected] pending trial login prevents duplicate submissions and closing', async ({ page }) => {
  let release, entered;
  const pending = new Promise(resolve => { release = resolve; });
  const started = new Promise(resolve => { entered = resolve; });
  let count = 0;
  await page.route('**/api/auth/trial-login', async route => {
    count += 1;
    entered();
    await pending;
    await route.fulfill({ status: 503, json: { message: '登录暂时不可用，请稍后重试。' } });
  });
  const dialog = await openTrial(page);
  await dialog.getByLabel('账号', { exact: true }).fill('GUI-injected-account');
  await dialog.getByLabel('密码', { exact: true }).fill('GUI-injected-password');
  await dialog.getByRole('button', { name: '登录', exact: true }).click();
  try {
    await started;
    await expect(dialog.getByRole('button', { name: '登录中…', exact: true })).toBeDisabled();
    await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeDisabled();
    await expect(dialog.getByLabel('账号', { exact: true })).toBeDisabled();
    await expect(dialog.getByLabel('密码', { exact: true })).toBeDisabled();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Escape');
    await expect(dialog).toBeVisible();
    expect(count).toBe(1);
  } finally { release(); }
  await expect(dialog.getByRole('alert')).toHaveText('登录暂时不可用，请稍后重试。');
  await expect(dialog.getByRole('button', { name: '登录', exact: true })).toBeEnabled();
});

test('[live-read] English trial dialog retains accessible labels and password semantics', async ({ page }) => {
  await open(page, '/auth?lang=en');
  await page.getByRole('button', { name: 'Shanghai Jiao Tong University emblem', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Trial account sign-in', exact: true });
  await expect(dialog.getByLabel('Account', { exact: true })).toBeFocused();
  await expect(dialog.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'password');
  await expect(dialog.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(dialog.getByText('Continue with your assigned trial account.', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
});

test('[live-read] required trial fields block blank submission in the browser', async ({ page }) => {
  let attempts = 0;
  await page.route('**/api/auth/trial-login', route => { attempts += 1; return route.fulfill({ status: 400, json: { message: 'Unexpected submission' } }); });
  const dialog = await openTrial(page);
  await dialog.getByRole('button', { name: '登录', exact: true }).click();
  await expect(dialog.getByLabel('账号', { exact: true })).toBeFocused();
  expect(attempts).toBe(0);
  await dialog.getByLabel('账号', { exact: true }).fill('GUI-never-submitted');
  await dialog.getByRole('button', { name: '登录', exact: true }).click();
  await expect(dialog.getByLabel('密码', { exact: true })).toBeFocused();
  expect(attempts).toBe(0);
});

test('[live-read] mobile public login and trial dialog fit the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, '/auth?lang=zh');
  await assertLayout(page);
  await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toBeInViewport();
  await emblem(page).click();
  const dialog = trialDialog(page);
  await expect(dialog).toBeInViewport();
  await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeInViewport();
  await expect(dialog.getByRole('button', { name: '登录', exact: true })).toBeInViewport();
  await assertLayout(page);
});

test('[live-read] public login and trial dialog pass serious accessibility checks', async ({ page }, info) => {
  await open(page, '/auth?lang=zh');
  await checkA11y(page, info);
  await emblem(page).click();
  await expect(trialDialog(page)).toBeVisible();
  await checkA11y(page, info);
  await page.keyboard.press('Escape');
  await expect(emblem(page)).toBeFocused();
});

test('[live-read] administrator entry returns to the public login through its visible link', async ({ page }) => {
  await open(page, '/admin/login');
  await page.getByRole('link', { name: '返回系统登录页', exact: true }).click();
  await expect(page).toHaveURL(/\/auth$/);
  await expect(page.getByRole('link', { name: /jAccount/ })).toBeVisible();
});
