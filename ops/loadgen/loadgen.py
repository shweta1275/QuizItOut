"""Steady synthetic traffic for the lab. Keeps running through app redeploys."""

import os
import random
import time

import requests

TARGET = os.getenv("TARGET", "http://host.docker.internal:8000")
RATE = float(os.getenv("RATE", "5"))
OMIT_COUNT_RATIO = float(os.getenv("OMIT_COUNT_RATIO", "0.4"))
REPORT_EVERY = 10.0


def pick_url() -> str:
    path = "/api/quiz/sample"
    return f"{TARGET}{path}" if random.random() < OMIT_COUNT_RATIO else f"{TARGET}{path}?count=3"


def main() -> None:
    sent = ok = err5xx = errors = 0
    last_report = time.monotonic()
    while True:
        started = time.monotonic()
        sent += 1
        try:
            status = requests.get(pick_url(), timeout=3).status_code
            if status >= 500:
                err5xx += 1
            elif status < 400:
                ok += 1
        except requests.RequestException:  # app is down for a few seconds during every redeploy
            errors += 1
        if started - last_report >= REPORT_EVERY:
            print(f"sent={sent} ok={ok} 5xx={err5xx} conn_errors={errors}", flush=True)
            sent = ok = err5xx = errors = 0
            last_report = started
        time.sleep(max(0.0, 1.0 / RATE - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
