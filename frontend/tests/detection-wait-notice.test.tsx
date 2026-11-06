import {render,screen} from '@testing-library/react';
import {expect,it} from 'vitest';
import {DetectionWaitNotice} from '../src/components/paperLint/DetectionWaitNotice';
it('makes the remaining-time estimate and completion email explicit',()=>{
  render(<DetectionWaitNotice eta={{status:'available',min_seconds:180,max_seconds:420,remaining_seconds:360,sample_count:5}} notification={{email:'123090058@link.cuhk.edu.cn',fixed:true,delivery_available:true}}/>);
  expect(screen.getByRole('status')).toHaveTextContent('系统正在检测中');
  expect(screen.getByText('预计还需约 6 分钟')).toBeVisible();
  expect(screen.getByText('检测完成后将通过邮件通知您')).toBeVisible();
  expect(screen.getByText('123090058@link.cuhk.edu.cn')).toBeVisible();
});
it('does not promise email delivery before sending has been configured',()=>{
  render(<DetectionWaitNotice eta={{status:'available',min_seconds:10,max_seconds:40,sample_count:4}} notification={{email:'123090058@link.cuhk.edu.cn',fixed:true,delivery_available:false}}/>);
  expect(screen.getByText('预计 1 分钟内完成')).toBeVisible();
  expect(screen.queryByText('检测完成后将通过邮件通知您')).not.toBeInTheDocument();
  expect(screen.getByText(/邮件通知暂未开通/)).toBeVisible();
  expect(screen.getByText(/无需停留在此页面/)).toBeVisible();
});
it('shows estimation and overtime states without a fabricated countdown',()=>{
  const {rerender}=render(<DetectionWaitNotice eta={{status:'estimating',sample_count:0}}/>);
  expect(screen.getByText('正在估算剩余时间')).toBeVisible();
  rerender(<DetectionWaitNotice eta={{status:'overdue',sample_count:4}}/>);
  expect(screen.getByText('用时比预计稍长，请耐心等待')).toBeVisible();
});
