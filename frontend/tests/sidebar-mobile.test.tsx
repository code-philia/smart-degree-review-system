import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it } from 'vitest';
import { Sidebar, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarTrigger, useSidebar } from '../src/components/shadcn/sidebar';

const originalWidth = window.innerWidth;
afterEach(() => { Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalWidth }); });

function Navigation() {
  const { setOpenMobile } = useSidebar();
  return <><Sidebar><SidebarMenu><SidebarMenuItem><SidebarMenuButton tooltip="历史报告" onClick={() => setOpenMobile(false)}>历史报告</SidebarMenuButton></SidebarMenuItem></SidebarMenu></Sidebar><SidebarTrigger /></>;
}

it('closes reopened mobile navigation on its first Escape after a focused menu choice', async () => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
  const user = userEvent.setup();
  render(<SidebarProvider><Navigation /></SidebarProvider>);
  await user.click(screen.getByRole('button', { name: '切换主导航' }));
  await user.click(within(await screen.findByRole('dialog', { name: '主导航' })).getByRole('button', { name: '历史报告' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: '切换主导航' }));
  const dialog = await screen.findByRole('dialog', { name: '主导航' });
  expect(within(dialog).getByRole('button', { name: '历史报告' })).toHaveFocus();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});
