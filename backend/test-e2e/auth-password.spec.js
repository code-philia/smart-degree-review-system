const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-AUTH-PASSWORD';
void reqId;

const validPassword = 'ArcDemo123!';

async function loginAsStudent(page, password = validPassword) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill('student01');
  await page.getByLabel('密码').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
}

test.describe('FEAT-AUTH-PASSWORD local account password scenarios', () => {
  test('FEAT-AUTH-PASSWORD:SCENARIO:001 logs in student01, creates HttpOnly session, and shows student home menu', async ({ page }) => {
    await loginAsStudent(page);

    await expect(page).toHaveURL(/\/$/);
    const roleMenu = page.getByRole('region', { name: '当前角色菜单' });
    await expect(roleMenu).toBeVisible();
    await expect(roleMenu.getByRole('heading', { name: '学生菜单' })).toBeVisible();
    await expect(roleMenu.getByText('数据范围：本学院')).toBeVisible();

    const cookies = await page.context().cookies();
    const sessionCookie = cookies.find((cookie) => cookie.name === 'arc_session');
    expect(sessionCookie).toBeTruthy();
    expect(sessionCookie.httpOnly).toBe(true);
    expect(sessionCookie.sameSite).toBe('Lax');

    const currentUserResponse = await page.request.get('/api/auth/me');
    expect(currentUserResponse.status()).toBe(200);
    expect(await currentUserResponse.json()).toEqual({
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

  test('FEAT-AUTH-PASSWORD:SCENARIO:002 rejects wrong password with the unified error and no session', async ({ page, request }) => {
    await loginAsStudent(page, 'WrongPassword123!');

    await expect(page).toHaveURL(/\/auth/);
    await expect(page.getByText('用户名或密码错误')).toBeVisible();
    await expect(page.getByText('已登录：student01（STUDENT）')).toHaveCount(0);
    await expect(page.getByRole('region', { name: '当前角色菜单' })).toHaveCount(0);

    const cookies = await page.context().cookies();
    expect(cookies.some((cookie) => cookie.name === 'arc_session')).toBe(false);

    const currentUserResponse = await request.get('/api/auth/me');
    expect(currentUserResponse.status()).toBe(401);
    const body = await currentUserResponse.json();
    expect(body).toMatchObject({ code: 401 });
    expect(body.user).toBeUndefined();
  });
});
