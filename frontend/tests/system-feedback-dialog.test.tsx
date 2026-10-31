import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SystemFeedbackDialog } from '../src/components/SystemFeedbackDialog';

const { submitSystemFeedback } = vi.hoisted(() => ({ submitSystemFeedback: vi.fn() }));
vi.mock('../src/api/feedback', () => ({ submitSystemFeedback }));

beforeEach(() => {
  submitSystemFeedback.mockReset();
  submitSystemFeedback.mockResolvedValue({ id: 'feedback-1', duplicate: false });
});

async function openFeedback() {
  const user = userEvent.setup();
  render(<SystemFeedbackDialog />);
  await user.click(screen.getByRole('button', { name: '使用反馈' }));
  return user;
}

describe('system feedback dialog', () => {
  it('requires a star rating and submits the keyboard-selected score and response-speed option', async () => {
    const user = await openFeedback();
    await user.click(screen.getByRole('button', { name: '提交反馈' }));
    expect(screen.getByRole('alert')).toHaveTextContent('请先选择满意度');
    expect(submitSystemFeedback).not.toHaveBeenCalled();

    const rating = screen.getByRole('radiogroup', { name: '整体满意度（必选）' });
    expect(rating).toHaveAttribute('aria-required', 'true');
    expect(within(rating).getAllByRole('radio')).toHaveLength(5);
    await user.click(within(rating).getByRole('radio', { name: '3 星' }));
    await user.keyboard('{ArrowRight}');
    expect(within(rating).getByRole('radio', { name: '4 星' })).toBeChecked();
    expect(within(rating).getByRole('radio', { name: '4 星' })).toHaveFocus();
    await user.click(screen.getByRole('checkbox', { name: '系统响应速度' }));
    await user.type(screen.getByRole('textbox', { name: '补充意见（可选）' }), '希望操作更流畅');
    await user.click(screen.getByRole('button', { name: '提交反馈' }));

    expect(submitSystemFeedback).toHaveBeenCalledWith({
      satisfaction_score: 4,
      improvement_areas: ['system_response_speed'],
      comment: '希望操作更流畅',
      request_id: expect.any(String),
    });
    expect(await screen.findByRole('status')).toHaveTextContent('感谢反馈！');
    expect(screen.queryByRole('button', { name: '提交反馈' })).not.toBeInTheDocument();
  });

  it('keeps a pending form open, blocks duplicate sends and reuses the request ID after a failed attempt', async () => {
    let rejectFirst!: (reason: Error) => void;
    submitSystemFeedback.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectFirst = reject;
        }),
    );
    const user = await openFeedback();
    await user.click(screen.getByRole('radio', { name: '5 星' }));
    await user.click(screen.getByRole('button', { name: '提交反馈' }));
    await user.click(screen.getByRole('button', { name: '提交中…' }));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '5 星' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled();
    expect(submitSystemFeedback).toHaveBeenCalledTimes(1);

    await act(async () => rejectFirst(new Error('网络连接中断')));
    expect(await screen.findByRole('alert')).toHaveTextContent('网络连接中断');
    expect(screen.getByRole('radio', { name: '5 星' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: '提交反馈' }));
    await screen.findByRole('status');
    expect(submitSystemFeedback).toHaveBeenCalledTimes(2);
    expect(submitSystemFeedback.mock.calls[1][0].request_id).toBe(submitSystemFeedback.mock.calls[0][0].request_id);
  });

  it('uses a new request ID for edited feedback and limits comments to the backend maximum', async () => {
    submitSystemFeedback.mockRejectedValueOnce(new Error('请稍后重试'));
    const user = await openFeedback();
    await user.click(screen.getByRole('radio', { name: '2 星' }));
    await user.click(screen.getByRole('button', { name: '提交反馈' }));
    await screen.findByRole('alert');
    const comment = screen.getByRole('textbox', { name: '补充意见（可选）' });
    expect(comment).toHaveAttribute('maxlength', '1000');
    await user.click(comment);
    await user.paste('改'.repeat(1001));
    expect(comment).toHaveValue('改'.repeat(1000));
    await user.click(screen.getByRole('button', { name: '提交反馈' }));
    await waitFor(() => expect(submitSystemFeedback).toHaveBeenCalledTimes(2));
    expect(submitSystemFeedback.mock.calls[1][0]).toMatchObject({ satisfaction_score: 2, comment: '改'.repeat(1000) });
    expect(submitSystemFeedback.mock.calls[1][0].request_id).not.toBe(submitSystemFeedback.mock.calls[0][0].request_id);
  });
});
