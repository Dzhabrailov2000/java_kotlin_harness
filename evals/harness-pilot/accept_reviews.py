#!/usr/bin/env python3
"""Import a judging batch only after explicit author inspection of that batch."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('batch');args=parser.parse_args()
    source=ROOT/'reviews'/args.batch
    assert source.parent==ROOT/'reviews'
    rows=json.loads(source.read_text());mapping=json.loads((ROOT/'blind-map.json').read_text())
    output=ROOT/'manual-review.json';accepted=json.loads(output.read_text()) if output.exists() else {}
    for row in rows:
        run_id=mapping[row['packet']]
        result=json.loads((ROOT/'runs'/run_id/'result.json').read_text())
        assert result['task_pass'] is None and result['review_schema_valid']
        assert isinstance(row['pass'],bool) and row['false_findings']>=0 and row['true_findings']>=0
        item={**row,'judge_source':'reviews/'+args.batch,'author_confirmed':True,
              'author_basis':'Submitted source/contract, actual review text, frozen fixture proof; no added scoring requirement.'}
        if run_id in accepted and accepted[run_id]!=item:raise RuntimeError('Refusing to silently replace accepted judgment: '+run_id)
        accepted[run_id]=item
    output.write_text(json.dumps(accepted,ensure_ascii=False,indent=2)+'\n')
    print('Accepted reviewed results:',len(accepted))


if __name__=='__main__':main()
