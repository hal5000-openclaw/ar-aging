#!/usr/bin/env python3
"""Accounts-receivable aging report from a CSV of invoices (stdlib only)."""
import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

BUCKETS = ["current", "1-30", "31-60", "61-90", "90+"]
REQUIRED = ["invoice", "client", "amount", "currency", "issued", "due"]


class InputError(Exception):
    """Raised for invalid input data."""


@dataclass
class Invoice:
    invoice: str
    client: str
    amount: Decimal
    currency: str
    issued: date
    due: date
    paid: date = None


def parse_date(value, line, field):
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise InputError(f"line {line}: invalid {field} date {value!r} (expected YYYY-MM-DD)")


def load_invoices(path):
    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as e:
        raise InputError(f"cannot read {path}: {e.strerror}")
    with fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise InputError("CSV file is empty")
        header = [h.strip().lower() for h in reader.fieldnames]
        missing = [c for c in REQUIRED if c not in header]
        if missing:
            raise InputError("missing required column(s): " + ", ".join(missing))
        invoices, seen = [], set()
        for row in reader:
            line = reader.line_num
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if None in row or not any(row.values()):
                continue
            for c in REQUIRED:
                if not row.get(c):
                    raise InputError(f"line {line}: empty value for {c!r}")
            if row["invoice"] in seen:
                raise InputError(f"line {line}: duplicate invoice {row['invoice']!r}")
            seen.add(row["invoice"])
            try:
                amount = Decimal(row["amount"])
                if not amount.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                raise InputError(f"line {line}: invalid amount {row['amount']!r}")
            if amount <= 0:
                raise InputError(f"line {line}: amount must be positive, got {row['amount']}")
            cur = row["currency"].upper()
            if len(cur) != 3 or not cur.isalpha():
                raise InputError(
                    f"line {line}: invalid currency {row['currency']!r} (expected 3 letters)")
            issued = parse_date(row["issued"], line, "issued")
            due = parse_date(row["due"], line, "due")
            if due < issued:
                raise InputError(f"line {line}: due date is before issued date")
            paid = parse_date(row["paid"], line, "paid") if row.get("paid") else None
            invoices.append(Invoice(row["invoice"], row["client"], amount, cur, issued, due, paid))
    return invoices


def bucket_for(days):
    if days <= 0:
        return "current"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def build_report(invoices, as_of):
    """Invoices paid on/before as_of are excluded. Totals are kept per currency."""
    currencies = {}
    for inv in invoices:
        if inv.paid is not None and inv.paid <= as_of:
            continue
        days = (as_of - inv.due).days
        b = bucket_for(days)
        c = currencies.setdefault(inv.currency, {
            "buckets": {k: Decimal(0) for k in BUCKETS},
            "clients": {}, "outstanding": Decimal(0), "invoices": []})
        c["buckets"][b] += inv.amount
        c["outstanding"] += inv.amount
        cl = c["clients"].setdefault(inv.client, {
            "buckets": {k: Decimal(0) for k in BUCKETS}, "total": Decimal(0)})
        cl["buckets"][b] += inv.amount
        cl["total"] += inv.amount
        c["invoices"].append({"invoice": inv.invoice, "client": inv.client,
                              "amount": inv.amount, "due": inv.due,
                              "days_overdue": max(days, 0), "bucket": b})
    return {"as_of": as_of, "currencies": dict(sorted(currencies.items()))}


def m(x):
    return f"{x:,.2f}"


def _rows(cur):
    rows = [[name] + [m(d["buckets"][b]) for b in BUCKETS] + [m(d["total"])]
            for name, d in sorted(cur["clients"].items())]
    rows.append(["TOTAL"] + [m(cur["buckets"][b]) for b in BUCKETS] + [m(cur["outstanding"])])
    return rows


HEAD = ["Client"] + BUCKETS + ["Total"]


def fmt_text(report):
    out = [f"Accounts receivable aging as of {report['as_of']}"]
    if not report["currencies"]:
        out.append("\nNo outstanding invoices.")
    for code, cur in report["currencies"].items():
        rows = [HEAD] + _rows(cur)
        w = [max(len(r[i]) for r in rows) for i in range(len(HEAD))]
        out.append(f"\n[{code}]")
        for n, r in enumerate(rows):
            if n == len(rows) - 1:
                out.append("-" * (sum(w) + 2 * (len(w) - 1)))
            out.append("  ".join(c.ljust(w[0]) if i == 0 else c.rjust(w[i]) for i, c in enumerate(r)))
            if n == 0:
                out.append("-" * (sum(w) + 2 * (len(w) - 1)))
        out.append(f"Outstanding total: {m(cur['outstanding'])} {code}")
    return "\n".join(out)


def fmt_markdown(report):
    out = [f"# Accounts receivable aging as of {report['as_of']}"]
    if not report["currencies"]:
        out.append("\nNo outstanding invoices.")
    for code, cur in report["currencies"].items():
        out.append(f"\n## {code}\n")
        out.append("| " + " | ".join(HEAD) + " |")
        out.append("|" + "---|" + "---:|" * (len(HEAD) - 1))
        rows = _rows(cur)
        for i, r in enumerate(rows):
            if i == len(rows) - 1:
                r = [f"**{c}**" for c in r]
            out.append("| " + " | ".join(r) + " |")
        out.append(f"\n**Outstanding total:** {m(cur['outstanding'])} {code}")
    return "\n".join(out)


def fmt_json(report):
    def conv(o):
        if isinstance(o, Decimal):
            return f"{o:.2f}"
        if isinstance(o, date):
            return o.isoformat()
        raise TypeError(type(o))
    return json.dumps(report, default=conv, indent=2)


def reminders(report):
    """One short, polite reminder per client with overdue invoices."""
    per = {}
    for code, cur in report["currencies"].items():
        for i in cur["invoices"]:
            if i["days_overdue"] > 0:
                per.setdefault(i["client"], []).append((code, i))
    out = []
    for client in sorted(per):
        items = sorted(per[client], key=lambda t: -t[1]["days_overdue"])
        lines = [f"Dear {client},", "",
                 "We hope you are well. Our records show the following invoice(s) "
                 f"past due as of {report['as_of']}:"]
        for code, i in items:
            lines.append(f"  - {i['invoice']}: {m(i['amount'])} {code}, due {i['due']} "
                         f"({i['days_overdue']} days overdue)")
        lines += ["If payment has already been sent, please disregard this note. "
                  "Otherwise we would be grateful if you could arrange payment soon.",
                  "", "Thank you very much,", "Accounts Receivable"]
        out.append("\n".join(lines))
    return "\n\n---\n\n".join(out) if out else "No overdue clients; no reminders needed."


def main(argv=None):
    p = argparse.ArgumentParser(description="Accounts-receivable aging report from a CSV.")
    p.add_argument("csv", help="invoice CSV: invoice,client,amount,currency,issued,due[,paid]")
    p.add_argument("--as-of", default=None, help="report date YYYY-MM-DD (default: today)")
    p.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    p.add_argument("--reminders", action="store_true",
                   help="print a payment reminder per overdue client")
    a = p.parse_args(argv)
    try:
        if a.as_of:
            try:
                as_of = date.fromisoformat(a.as_of)
            except ValueError:
                raise InputError(f"invalid --as-of date {a.as_of!r} (expected YYYY-MM-DD)")
        else:
            as_of = date.today()
        report = build_report(load_invoices(a.csv), as_of)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print({"text": fmt_text, "json": fmt_json, "markdown": fmt_markdown}[a.format](report))
    if a.reminders:
        print("\n=== Payment reminders ===\n")
        print(reminders(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
