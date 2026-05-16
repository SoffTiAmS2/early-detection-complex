from __future__ import annotations

import os
import time
from pathlib import Path

from center.core.paths import DEFAULT_STORE
from center.persistence.honeypot_logs import normalize_pending_raw_logs


STORE = Path(DEFAULT_STORE)


def main() -> None:
    interval = float(os.environ.get("NORMALIZER_INTERVAL_SECONDS", "5"))
    batch_size = int(os.environ.get("NORMALIZER_BATCH_SIZE", "500"))
    print(f"log-normalizer: interval={interval}s batch_size={batch_size}")
    while True:
        normalized = normalize_pending_raw_logs(STORE, batch_size)
        if normalized:
            print(f"log-normalizer: normalized={normalized}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
