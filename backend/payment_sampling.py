"""Bound the payment graph while preserving each company's strongest links."""

import csv
import heapq
from decimal import Decimal
from pathlib import Path


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        yield from csv.DictReader(stream, dialect=csv.Sniffer().sniff(sample, delimiters=";,\t"))


def _top_payment_rows(path, company_column, limit):
    heaps = {}
    total_rows = 0
    for row_number, row in enumerate(csv_rows(path), 1):
        total_rows = row_number
        company = row[company_column]
        if not company:
            continue
        heap = heaps.setdefault(company, [])
        candidate = (Decimal(row["PAY_AMT"]), row_number)
        if len(heap) < limit:
            heapq.heappush(heap, candidate)
        elif candidate > heap[0]:
            heapq.heapreplace(heap, candidate)
    return {row_number for heap in heaps.values() for _, row_number in heap}, total_rows


def select_payment_rows(path, per_company_direction):
    """Return source row numbers for top payments per payer and beneficiary."""
    if per_company_direction < 1:
        raise ValueError("per_company_direction must be positive")
    outgoing, total_rows = _top_payment_rows(path, "PAYER", per_company_direction)
    incoming, _ = _top_payment_rows(path, "BENEFICIARY", per_company_direction)
    return outgoing | incoming, total_rows
