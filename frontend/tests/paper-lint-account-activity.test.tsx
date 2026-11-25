import { renderHook, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { usePaperLintActivity } from '../src/hooks/usePaperLintActivity';
import { fetchPaperLintActivity } from '../src/api/paperLint';

vi.mock('../src/api/paperLint', async () => ({ ...await vi.importActual('../src/api/paperLint'), fetchPaperLintActivity: vi.fn() }));

it('keeps a closed or unauthenticated activity consumer idle and clears it when disabled again', async () => {
  vi.mocked(fetchPaperLintActivity).mockResolvedValue({user_id:'student',limited:false,busy:false,uploading:false,active_job:null});
  const hook=renderHook(({owner}:{owner:string|undefined})=>usePaperLintActivity(owner),{initialProps:{owner:undefined as string|undefined}});
  expect(hook.result.current.activity).toBeNull();
  expect(fetchPaperLintActivity).not.toHaveBeenCalled();
  hook.rerender({owner:'student'});
  await waitFor(()=>expect(hook.result.current.activity?.user_id).toBe('student'));
  hook.rerender({owner:undefined});
  expect(hook.result.current.activity).toBeNull();
});
