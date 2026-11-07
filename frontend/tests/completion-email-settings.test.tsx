import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect,it,vi,afterEach} from 'vitest';
import {CompletionEmailSettings} from '../src/components/paperLint/CompletionEmailSettings';
import {fetchCompletionNotification,saveCompletionEmail} from '../src/api/reportNotifications';
vi.mock('../src/api/reportNotifications',()=>({fetchCompletionNotification:vi.fn(),saveCompletionEmail:vi.fn()}));
afterEach(()=>vi.resetAllMocks());
it('displays the fixed local-account destination without an editable field',async()=>{
  vi.mocked(fetchCompletionNotification).mockResolvedValue({email:'123090058@link.cuhk.edu.cn',fixed:true,delivery_available:false});
  render(<CompletionEmailSettings userId="student01" busy={false} onChange={()=>{}}/>);
  expect(await screen.findByText('123090058@link.cuhk.edu.cn')).toBeVisible();
  expect(screen.getByText('邮件通知暂未开通')).toBeVisible();expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
it('lets an account with no mailbox save a destination for its report notifications',async()=>{
  vi.mocked(fetchCompletionNotification).mockResolvedValue({email:null,fixed:false,delivery_available:true});
  vi.mocked(saveCompletionEmail).mockResolvedValue({email:'mine@example.test',fixed:false,delivery_available:true});
  render(<CompletionEmailSettings userId="legacy-user" busy={false} onChange={()=>{}}/>);
  const user=userEvent.setup();await user.type(await screen.findByRole('textbox',{name:'接收通知邮箱'}),'mine@example.test');
  await user.click(screen.getByRole('button',{name:'保存邮箱'}));
  await waitFor(()=>expect(screen.getByText('mine@example.test')).toBeVisible());expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
