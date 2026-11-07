import {render,screen} from '@testing-library/react';
import {expect,it} from 'vitest';
import {DetectionWaitNotice} from '../src/components/paperLint/DetectionWaitNotice';
it('shows the requested completion message and one numeric ETA',()=>{
  render(<DetectionWaitNotice eta={{status:'available',min_seconds:180,max_seconds:420,remaining_seconds:360,sample_count:5}}/>);
  expect(screen.getByRole('status')).toHaveTextContent('系统正在检测中');
  expect(screen.getByText('预计还需约 6 分钟')).toBeVisible();
  expect(screen.getByText('系统正在检测中，检测完成后将通过邮件通知您')).toBeVisible();
  expect(screen.queryByText(/123090058/)).not.toBeInTheDocument();
});
it('keeps the card free of mailbox settings and service configuration badges',()=>{
  render(<DetectionWaitNotice eta={{status:'available',min_seconds:10,max_seconds:40,sample_count:4}}/>);
  expect(screen.getByText('预计 1 分钟内完成')).toBeVisible();
  expect(screen.queryByText(/邮件通知暂未开通/)).not.toBeInTheDocument();
});
it('updates the minute value when the server revises its estimate',()=>{
  const {rerender}=render(<DetectionWaitNotice eta={{status:'estimating',sample_count:0}}/>);
  expect(screen.getByText('正在估算剩余时间')).toBeVisible();
  rerender(<DetectionWaitNotice eta={{status:'available',remaining_seconds:120,sample_count:4}}/>);
  expect(screen.getByText('预计还需约 2 分钟')).toBeVisible();
  rerender(<DetectionWaitNotice eta={{status:'available',remaining_seconds:240,sample_count:4}}/>);
  expect(screen.getByText('预计还需约 4 分钟')).toBeVisible();
  expect(screen.queryByText(/用时比预计稍长/)).not.toBeInTheDocument();
});
