import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { FindingFeedback } from '../src/api/feedback';
import { FeedbackControls } from '../src/components/paperLint/FeedbackControls';

const negativeFeedback: FindingFeedback = {
  id: 'feedback-1',
  feedback_value: 'negative',
  reason_code: 'other',
  reason_text: '原有说明',
  created_at: '2026-10-31T00:00:00Z',
  updated_at: '2026-10-31T00:00:00Z',
};

function deferred() {
  let resolve!: () => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<void>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, resolve, reject };
}

type ControlsProps = {
  feedback?: FindingFeedback | null;
  onValue?: (value: 'positive' | 'negative') => void | Promise<void>;
  onReason?: (code: string | null, text: string | null) => void | Promise<void>;
  onCancel?: () => void | Promise<void>;
  onActivate?: () => void;
};

function renderControls({
  feedback = negativeFeedback,
  onValue = () => {},
  onReason = () => {},
  onCancel = () => {},
  onActivate = () => {},
}: ControlsProps = {}) {
  return render(
    <article
      role="button"
      tabIndex={0}
      onClick={onActivate}
      onKeyDown={(event) => {
        if (event.key === ' ' || event.key === 'Enter') {
          event.preventDefault();
          onActivate();
        }
      }}
    >
      <FeedbackControls
        label="这个问题的判断是否准确？"
        feedback={feedback}
        reasons={[
          ['false_positive', '误报'],
          ['other', '其他'],
        ]}
        onValue={onValue}
        onReason={onReason}
        onCancel={onCancel}
      />
    </article>,
  );
}

function submitButton() {
  return screen.getByRole('button', { name: '提交反馈' });
}

describe('paper lint feedback submission', () => {
  it('locks the pending submission and submits the edited reason once', async () => {
    const user = userEvent.setup();
    const request = deferred();
    const onReason = vi.fn(() => request.promise);
    renderControls({ onReason });
    await user.selectOptions(screen.getByRole('combobox', { name: '负面反馈原因' }), 'false_positive');
    await user.clear(screen.getByRole('textbox', { name: '反馈补充说明' }));
    await user.type(screen.getByRole('textbox', { name: '反馈补充说明' }), '引用其实准确');
    const button = submitButton();
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });

    expect(onReason).toHaveBeenCalledTimes(1);
    expect(onReason).toHaveBeenCalledWith('false_positive', '引用其实准确');
    expect(screen.getByRole('button', { name: '提交中…' })).toBeDisabled();
    expect(screen.getByRole('combobox', { name: '负面反馈原因' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: '反馈补充说明' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '有帮助' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '取消评价' })).toBeDisabled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await act(async () => request.resolve());
    expect(await screen.findByRole('dialog', { name: '提交成功' })).toBeInTheDocument();
  });

  it('shows success only after the reason callback resolves and lets the user close it', async () => {
    const user = userEvent.setup();
    const request = deferred();
    renderControls({ onReason: () => request.promise });
    await user.click(submitButton());
    expect(screen.queryByRole('dialog', { name: '提交成功' })).not.toBeInTheDocument();
    await act(async () => request.resolve());
    const dialog = await screen.findByRole('dialog', { name: '提交成功' });
    await user.click(within(dialog).getByRole('button', { name: '知道了' }));
    expect(screen.queryByRole('dialog', { name: '提交成功' })).not.toBeInTheDocument();
  });

  it('keeps a rejected reason editable, shows the error inline, and succeeds on retry', async () => {
    const user = userEvent.setup();
    const request = deferred();
    const onReason = vi
      .fn()
      .mockImplementationOnce(() => request.promise)
      .mockResolvedValue(undefined);
    renderControls({ onReason });
    await user.click(submitButton());
    await act(async () => request.reject(new Error('反馈暂时无法保存')));
    expect(await screen.findByRole('alert')).toHaveTextContent('反馈暂时无法保存');
    expect(screen.queryByRole('dialog', { name: '提交成功' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '反馈补充说明' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: '提交反馈' }));
    expect(await screen.findByRole('dialog', { name: '提交成功' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(onReason).toHaveBeenCalledTimes(2);
  });

  it('keeps spaces and Enter in the editor from activating the finding article', async () => {
    const user = userEvent.setup();
    const onActivate = vi.fn();
    renderControls({ onActivate });
    const textarea = screen.getByRole('textbox', { name: '反馈补充说明' });
    await user.clear(textarea);
    await user.type(textarea, '引用 已核对{Enter}第二行');
    expect(textarea).toHaveValue('引用 已核对\n第二行');
    fireEvent.keyDown(screen.getByRole('combobox', { name: '负面反馈原因' }), { key: ' ' });
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('limits pasted supplemental text to the backend limit of 1000 characters', async () => {
    const user = userEvent.setup();
    renderControls();
    const textarea = screen.getByRole('textbox', { name: '反馈补充说明' });
    await user.clear(textarea);
    await user.paste('字'.repeat(1001));
    expect(textarea).toHaveValue('字'.repeat(1000));
  });

  it('restores saved reasons when feedback changes and preserves evaluation controls', async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    const onCancel = vi.fn();
    const props = {
      label: '这条修复建议是否有帮助？',
      reasons: [['other', '其他']] as [string, string][],
      onValue,
      onReason: () => {},
      onCancel,
    };
    const { rerender } = render(<FeedbackControls {...props} feedback={negativeFeedback} />);
    expect(screen.getByRole('button', { name: '需要改进' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('combobox', { name: '负面反馈原因' })).toHaveValue('other');
    expect(screen.getByRole('textbox', { name: '反馈补充说明' })).toHaveValue('原有说明');
    await user.clear(screen.getByRole('textbox', { name: '反馈补充说明' }));
    await user.type(screen.getByRole('textbox', { name: '反馈补充说明' }), '未提交草稿');
    rerender(
      <FeedbackControls
        {...props}
        feedback={{ ...negativeFeedback, id: 'feedback-2', reason_code: null, reason_text: '重新载入的说明' }}
      />,
    );
    expect(screen.getByRole('combobox', { name: '负面反馈原因' })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: '反馈补充说明' })).toHaveValue('重新载入的说明');
    await user.click(screen.getByRole('button', { name: '有帮助' }));
    expect(onValue).toHaveBeenLastCalledWith('positive');
    await user.click(screen.getByRole('button', { name: '需要改进' }));
    expect(onValue).toHaveBeenLastCalledWith('negative');
    await user.click(screen.getByRole('button', { name: '取消评价' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    rerender(<FeedbackControls {...props} feedback={{ ...negativeFeedback, feedback_value: 'positive' }} />);
    expect(screen.getByRole('button', { name: '有帮助' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('textbox', { name: '反馈补充说明' })).not.toBeInTheDocument();
    rerender(<FeedbackControls {...props} feedback={null} />);
    expect(screen.queryByRole('button', { name: '取消评价' })).not.toBeInTheDocument();
  });

  it.each(['value', 'cancel'] as const)(
    'handles rejected asynchronous %s callbacks without an unhandled rejection',
    async (action) => {
      const user = userEvent.setup();
      const request = deferred();
      const callback = vi
        .fn()
        .mockImplementationOnce(() => request.promise)
        .mockResolvedValue(undefined);
      renderControls(action === 'value' ? { onValue: callback } : { onCancel: callback });
      const button = screen.getByRole('button', { name: action === 'value' ? '有帮助' : '取消评价' });
      await user.click(button);
      expect(button).toBeDisabled();
      await act(async () => request.reject(new Error('网络暂不可用')));
      expect(await screen.findByRole('alert')).toHaveTextContent('网络暂不可用');
      expect(button).toBeEnabled();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      await user.click(button);
      await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
      expect(callback).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    },
  );

  it('accepts synchronous reason callbacks and submits blank optional fields as null', async () => {
    const user = userEvent.setup();
    const onReason = vi.fn();
    renderControls({ feedback: { ...negativeFeedback, reason_code: null, reason_text: null }, onReason });
    await user.click(submitButton());
    expect(onReason).toHaveBeenCalledWith(null, null);
    expect(await screen.findByRole('dialog', { name: '提交成功' })).toBeInTheDocument();
  });

  it('disables submission when no reason callback is available', () => {
    render(
      <FeedbackControls
        label="反馈"
        feedback={negativeFeedback}
        reasons={[['other', '其他']]}
        onValue={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(submitButton()).toBeDisabled();
    fireEvent.click(submitButton());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps dialog keyboard actions inside the dialog and restores focus to submit', async () => {
    const user = userEvent.setup();
    const onActivate = vi.fn();
    renderControls({ onActivate });
    const submit = submitButton();
    await user.click(submit);
    const dialog = await screen.findByRole('dialog', { name: '提交成功' });
    const close = within(dialog).getByRole('button', { name: '知道了' });
    await waitFor(() => expect(close).toHaveFocus());
    await user.tab();
    expect(close).toHaveFocus();
    await user.keyboard(' ');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(submit).toHaveFocus());
    expect(onActivate).not.toHaveBeenCalled();
    await user.click(submit);
    await screen.findByRole('dialog', { name: '提交成功' });
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(onActivate).not.toHaveBeenCalled();
  });
});
