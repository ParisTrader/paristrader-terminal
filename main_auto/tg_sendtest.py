"""
Helper script to trigger a single Mode 2-style generation + Telegram send
without waiting for the scheduled windows. Useful for testing.
"""

from main_auto import current_time, run_pipeline_with_retries


def main() -> None:
    run_time = current_time()
    print("[TEST] Running scheduled-mode pipeline immediately...")
    run_pipeline_with_retries(run_time=run_time, send_telegram=True)
    print("[TEST] tg_sendtest run complete.")


if __name__ == "__main__":
    main()

