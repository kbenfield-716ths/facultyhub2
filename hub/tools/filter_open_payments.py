#!/usr/bin/env python3
"""Cut a CMS Open Payments CSV (often several GB) down to the rows for your faculty's NPIs.

  1. In Faculty Hub, Admin > Open Payments, download the NPI list (npis.txt).
  2. python3 tools/filter_open_payments.py OP_DTL_GNRL_PGYR2025_P06302026.csv npis.txt filtered_general.csv
  3. Upload filtered_general.csv in Admin > Open Payments. Repeat for the research and ownership files.

Runs on your own computer, reads the file line by line, and keeps the header plus matching rows only.
"""
import csv, sys

NPI_COLS = ("covered_recipient_npi", "physician_npi", "principal_investigator_1_npi")


def main(src, npis_path, dst):
    want = {l.strip() for l in open(npis_path) if l.strip()}
    csv.field_size_limit(10_000_000)
    kept = read = 0
    with open(src, newline="", encoding="utf-8-sig", errors="replace") as f, open(dst, "w", newline="", encoding="utf-8") as o:
        rd = csv.reader(f)
        head = next(rd)
        w = csv.writer(o)
        w.writerow(head)
        idx = [i for i, h in enumerate(head) if h.strip().lower() in NPI_COLS]
        if not idx:
            sys.exit("No NPI column found. Is this a CMS Open Payments file?")
        for row in rd:
            read += 1
            if any(i < len(row) and row[i].strip() in want for i in idx):
                w.writerow(row)
                kept += 1
    print(f"read {read:,} rows, kept {kept:,} for {len(want)} NPIs -> {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
