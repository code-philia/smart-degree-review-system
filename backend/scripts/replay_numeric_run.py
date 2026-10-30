"""Replay a recorded numeric run without calling any API."""
import argparse
import json

from numeric_consistency import run_numeric
from numeric_run_trace import load_replay


def replay(directory):
    manifest, artifacts = load_replay(directory)
    ir = artifacts['paper_model'][0]
    context = artifacts['context'][0]
    inputs = iter(artifacts.get('call_input', []))
    outputs = iter(artifacts.get('call_result', []))
    def request(messages):
        recorded_input = next(inputs)
        if messages != recorded_input['messages']:
            raise ValueError('Replay input changed: prompt, context or retrieval version differs')
        try:
            result = next(outputs)
        except StopIteration:
            raise RuntimeError('Recorded call failed; see call_error artifacts')
        return result['parsed'], result['usage']
    return run_numeric(ir, {'chinese_abstract': context['abstract']}, request,
                       verification_mode=manifest.get('versions', {}).get('verification_mode', 'batch'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory')
    args = parser.parse_args()
    print(json.dumps(replay(args.run_directory), ensure_ascii=False, allow_nan=False))
