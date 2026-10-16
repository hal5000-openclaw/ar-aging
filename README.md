# ar-aging

A small, stdlib-only Python 3 CLI that turns a CSV of invoices into an accounts-receivable aging report, with optional polite payment-reminder text.

## Why

Spreadsheets for aging reports get fiddly. This is one file with no dependencies that you can run anywhere Python 3.8+ is installed.

## Install

No install needed. Copy `ar_aging.py` or clone the repo.

## Input

CSV with header `invoice,client,amount,currency,issued,due,paid`. Dates are `YYYY-MM-DD`; `paid` is optional and may be blank.

- Invoices with a `paid` date on or before `--as-of` are excluded. A paid date after `--as-of` counts as still outstanding.
- Days overdue = `--as-of` minus `due`. Buckets: current (not yet overdue or due today), 1-30, 31-60, 61-90, 90+.
- Totals are kept separately per currency (no conversion).
- Bad input (missing columns, bad amounts/dates/currency, due before issued, duplicate invoice IDs) exits with code 2 and a message naming the line.

## Usage

```
python ar_aging.py FILE.csv [--as-of YYYY-MM-DD] [--format text|json|markdown] [--reminders]
```

Example (`examples/invoices.csv`):

```
$ python ar_aging.py examples/invoices.csv --as-of 2026-10-16
Accounts receivable aging as of 2026-10-16

[EUR]
Client   current    1-30  31-60  61-90   90+   Total
----------------------------------------------------
Initech     0.00  980.00   0.00   0.00  0.00  980.00
----------------------------------------------------
TOTAL       0.00  980.00   0.00   0.00  0.00  980.00
Outstanding total: 980.00 EUR

[USD]
Client         current  1-30   31-60     61-90       90+     Total
------------------------------------------------------------------
Acme Corp     1,200.00  0.00  800.50      0.00      0.00  2,000.50
Globex            0.00  0.00    0.00  2,500.00    300.00  2,800.00
Umbrella Ltd     75.00  0.00    0.00      0.00  4,000.00  4,075.00
------------------------------------------------------------------
TOTAL         1,275.00  0.00  800.50  2,500.00  4,300.00  8,875.50
Outstanding total: 8,875.50 USD
```

With `--reminders`, a short message per client with overdue invoices follows the report:

```
Dear Acme Corp,

We hope you are well. Our records show the following invoice(s) past due as of 2026-10-16:
  - INV-002: 800.50 USD, due 2026-09-14 (32 days overdue)
If payment has already been sent, please disregard this note. Otherwise we would be grateful if you could arrange payment soon.

Thank you very much,
Accounts Receivable
```

## Tests

```
python3 -m unittest -v
```

## License

MIT
