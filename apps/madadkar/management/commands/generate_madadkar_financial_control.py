"""Generate Madadkar financial operations control snapshot."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from apps.madadkar.services import generate_financial_control_snapshot


class Command(BaseCommand):
    """Generate one finance-ops control snapshot for operational review."""

    help = "Generate Madadkar financial operations control snapshot."

    def handle(self, *args: Any, **options: Any) -> None:
        snapshot = generate_financial_control_snapshot(generated_by_task_id="management_command")
        self.stdout.write(
            json.dumps(
                {
                    "snapshot_id": snapshot.pk,
                    "generated_for_date": snapshot.generated_for_date.isoformat(),
                    "severity": snapshot.severity,
                    "summary": snapshot.summary,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
        )
