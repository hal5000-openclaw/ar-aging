import json
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal

import ar_aging as ar

SAMPLE = os.path.join(os.path.dirname(__file__), "examples", "invoices.csv")
D = date(2026, 10, 16)


def write(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    f.write(text)
    f.close()
    return f.name


HDR = "invoice,client,amount,currency,issued,due,paid\n"


class T(unittest.TestCase):
    def test_buckets(self):
        for days, b in [(-5, "current"), (0, "current"), (1, "1-30"), (30, "1-30"),
                        (31, "31-60"), (60, "31-60"), (61, "61-90"), (90, "61-90"), (91, "90+")]:
            self.assertEqual(ar.bucket_for(days), b)

    def test_sample_report(self):
        r = ar.build_report(ar.load_invoices(SAMPLE), D)
        usd = r["currencies"]["USD"]
        self.assertEqual(usd["buckets"], {"current": Decimal("1275.00"), "1-30": Decimal("0.00"),
                                          "31-60": Decimal("800.50"), "61-90": Decimal("2500.00"),
                                          "90+": Decimal("4300.00")})
        self.assertEqual(usd["outstanding"], Decimal("8875.50"))
        self.assertEqual(usd["clients"]["Globex"]["total"], Decimal("2800.00"))
        self.assertNotIn("Initech", usd["clients"])  # paid invoice excluded
        self.assertEqual(r["currencies"]["EUR"]["buckets"]["1-30"], Decimal("980.00"))

    def test_paid_after_as_of_is_outstanding(self):
        p = write(HDR + "A,X,10,USD,2026-01-01,2026-02-01,2026-12-01\n")
        r = ar.build_report(ar.load_invoices(p), D)
        self.assertEqual(r["currencies"]["USD"]["buckets"]["90+"], Decimal(10))

    def test_formats_and_reminders(self):
        r = ar.build_report(ar.load_invoices(SAMPLE), D)
        self.assertIn("Outstanding total: 8,875.50 USD", ar.fmt_text(r))
        self.assertIn("| Client |", ar.fmt_markdown(r))
        self.assertEqual(json.loads(ar.fmt_json(r))["currencies"]["USD"]["outstanding"], "8875.50")
        rem = ar.reminders(r)
        self.assertIn("Dear Globex", rem)
        self.assertIn("Dear Initech", rem)  # EUR overdue
        self.assertNotIn("INV-001", rem)  # not yet due

    def bad(self, text, msg):
        with self.assertRaises(ar.InputError) as c:
            ar.load_invoices(write(text))
        self.assertIn(msg, str(c.exception))

    def test_validation(self):
        self.bad("invoice,client\nA,B\n", "missing required column")
        self.bad(HDR + "A,X,abc,USD,2026-01-01,2026-02-01,\n", "invalid amount")
        self.bad(HDR + "A,X,-5,USD,2026-01-01,2026-02-01,\n", "positive")
        self.bad(HDR + "A,X,5,US,2026-01-01,2026-02-01,\n", "currency")
        self.bad(HDR + "A,X,5,USD,01/01/2026,2026-02-01,\n", "issued")
        self.bad(HDR + "A,X,5,USD,2026-03-01,2026-02-01,\n", "before issued")
        self.bad(HDR + "A,X,5,USD,2026-01-01,2026-02-01,\nA,X,5,USD,2026-01-01,2026-02-01,\n", "duplicate")
        self.bad(HDR + "A,,5,USD,2026-01-01,2026-02-01,\n", "empty value")

    def test_cli(self):
        self.assertEqual(ar.main([SAMPLE, "--as-of", "2026-10-16", "--reminders"]), 0)
        self.assertEqual(ar.main([SAMPLE, "--as-of", "nope"]), 2)
        self.assertEqual(ar.main(["/nonexistent.csv"]), 2)


if __name__ == "__main__":
    unittest.main()
