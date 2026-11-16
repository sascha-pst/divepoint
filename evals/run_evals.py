"""Offline scaffold smoke check; this does NOT measure PRD acceptance metrics."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--quick', action='store_true')
parser.parse_args()
rows = [json.loads(line) for line in Path(__file__).with_name('places.jsonl').read_text().splitlines()]
assert rows and all(row['prompt'] and row['expected_type'] in {'dive', 'clarify', 'reject'} for row in rows)
print(f'PASS: {len(rows)} seed cases are well formed. Place/guide quality evaluation is not implemented.')
