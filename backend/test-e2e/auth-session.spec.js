const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-AUTH-SESSION';
void reqId;

const demoPassword = 'ArcDemo123!';

test.describe('FEAT-AUTH-SESSION scenarios', () => {
  test('FEAT-AUTH-SESSION:SCENARIO:001 restores student01 session after refresh and current-user requests', async ({ page, request }) => {
    await page.goto('/auth');
    await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();

    await page.getByLabel('账号').fill('student01');
    await page.getByLabel('密码').fill(demoPassword);
    await page.getByRole('button', { name: '登录' }).click();

    await expect(page.getByText('已登录：student01（STUDENT）')).toBeVisible();

    await page.reload();
    await expect(page.getByText('已登录：student01（STUDENT）')).toBeVisible();

    const currentUserResponse = await request.get('/api/auth/me');
    expect(currentUserResponse.status()).toBe(200);
    await expect(currentUserResponse).toHaveJSON({
      user: {
        id: 'student01',
        username: 'student01',
        role: 'STUDENT',
        collegeId: 'college01',
        supervisorId: 'supervisor01',
        scope: 'COLLEGE',
      },
    });
  });

  test('FEAT-AUTH-SESSION:SCENARIO:002 rejects unauthenticated protected business API access without data', async ({ request }) => {
    const currentUserResponse = await request.get('/api/auth/me');
    expect(currentUserResponse.status()).toBe(401);

    const body = await currentUserResponse.json();
    expect(body).toMatchObject({ code: 401 });
    expect(body.user).toBeUndefined();
    expect(body.records).toBeUndefined();
  });
});
