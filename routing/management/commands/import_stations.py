import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from routing.models import FuelStation
from routing.services import cities

MIN_PRICE, MAX_PRICE = Decimal("1.50"), Decimal("8.00")


def fix_text(s: str) -> str:
    s = (s or "").strip()
    try:  # repair mojibake such as "Stuckeyâ€™s"
        s = s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return " ".join(s.split())


class Command(BaseCommand):
    help = "Import fuel stations from the CSV, dedupe, drop non-US rows, geocode offline."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=str(Path(settings.BASE_DIR) / "data" / "fuel-prices-for-be-assessment.csv"))

    def handle(self, *args, **opts):
        us_states = cities.states()
        by_id = defaultdict(list)
        stats = defaultdict(int)
        with open(opts["csv"], newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                state = row["State"].strip().upper()
                if state not in us_states:
                    stats["non_us"] += 1
                    continue
                price = Decimal(row["Retail Price"])
                if not (MIN_PRICE <= price <= MAX_PRICE):
                    stats["bad_price"] += 1
                    continue
                by_id[int(row["OPIS Truckstop ID"])].append((row, price))

        objs = []
        for opis_id, rows in by_id.items():
            row = rows[0][0]
            city = fix_text(row["City"])
            pt = cities.lookup(city, row["State"])
            if not pt:
                stats["no_geocode"] += 1
                continue
            price = min(p for _, p in rows)  # cheapest quoted price per station
            objs.append(FuelStation(
                opis_id=opis_id, name=fix_text(row["Truckstop Name"]),
                address=fix_text(row["Address"]), city=city, state=row["State"].strip().upper(),
                price=price.quantize(Decimal("0.0001")), lat=pt[0], lng=pt[1]))
        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(objs, batch_size=1000)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(objs)} stations; skipped: {dict(stats)}"))
