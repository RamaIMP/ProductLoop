"""Import a specific saved development-report snapshot without inventing unit links."""
import json
import sys
from app.services.lifecycle import get_store


def main(path):
    with open(path) as file:
        reports = json.load(file)
    store = get_store()
    count = 0
    for report in reports:
        if store.get('complaints',report['report_id']):
            continue
        # These snapshots contain confirmed reports only. Exact historical
        # submission timestamps were not captured; preserve that uncertainty.
        report = {**report, 'submitted_at':None, 'legacy_confirmed':True}
        if report.get('callback'):
            report['callback'] = {**report['callback'],'status':'demo_requested','time_zone':'Asia/Kolkata'}
        store.save_report(report,'legacy_report_imported')
        count += 1
    print(f'Imported {count} legacy confirmed reports; no product/media links fabricated.')


if __name__ == '__main__':
    main(sys.argv[1])
