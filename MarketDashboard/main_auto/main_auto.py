import argparse
import mimetypes
import sys
import time
import uuid
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 on Windows
    ZoneInfo = None  # type: ignore[misc, assignment]

from ETF_sector_heatmap import generate_etf_sector_heatmap
from SPX_VIX import generate_spx_vix_chart
from market_breadth_hsi import generate_market_breadth_hsi
from market_breadth_nq import generate_market_breadth_nq

import CBBC
from OtmPremium import generate_otm_premium_dashboard
import Index_day_range
import Index_Tradingtime

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

TZ_NAME = "Asia/Hong_Kong"
LOCAL_TZ = ZoneInfo(TZ_NAME) if ZoneInfo is not None else None

ACTIVE_WEEKDAYS = {1, 2, 3, 4, 5, 6}  # Monday (1) through Saturday (6)


def _build_run_times():
    tzinfo = LOCAL_TZ if LOCAL_TZ else None
    return (
        dt_time(hour=9, minute=0, tzinfo=tzinfo),
        dt_time(hour=22, minute=30, tzinfo=tzinfo),
        dt_time(hour=23, minute=30, tzinfo=tzinfo),
    )


RUN_TIMES = _build_run_times()

# Allow overriding the default mode directly in code for convenience:
# "1" = immediate run, "2" = scheduled mode (Mon-Sat 09:00/22:30/23:30 HKT).
DEFAULT_MODE = "1"

# ==================== TELEGRAM SETTINGS ====================
TELEGRAM_TOKEN = "8523931731:AAEtoq7TfO-sr9BIAUe-G9FvETj0_g7NMIc"
CHAT_ID = -1003261897616
TOPIC_ID = 4725
TELEGRAM_MAX_SEND_RETRIES = 5


def build_dashboard_html(
    etf_html: Path,
    hsi_png: Path,
    nq_png: Path,
    spx_vix_png: Path,
    dashboard_file: Path,
    cbbc_html: Optional[Path] = None,
    otm_html: Optional[Path] = None,
    true_range_data: Optional[list] = None,
    trading_time_data: Optional[list] = None,
) -> Path:
    """
    Assemble the unified dashboard HTML file referencing the generated assets.
    """
    import base64
    import html as html_module

    def png_to_data_uri(image_path: Path) -> str:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    etf_inner_html = etf_html.read_text(encoding="utf-8")
    etf_srcdoc = html_module.escape(etf_inner_html, quote=True)
    hsi_data_uri = png_to_data_uri(hsi_png)
    nq_data_uri = png_to_data_uri(nq_png)
    spx_data_uri = png_to_data_uri(spx_vix_png)
    cbbc_options_html = ""
    cbbc_sections_html = ""

    if cbbc_html is not None and cbbc_html.exists():
        cbbc_inner_html = cbbc_html.read_text(encoding="utf-8")
        cbbc_srcdoc = html_module.escape(cbbc_inner_html, quote=True)
        cbbc_options_html = """
                <option value="cbbc_ladder">HSI CBBC Knock-Out Ladder</option>"""
        cbbc_sections_html = f"""
        <section class="view hidden" data-view="cbbc_ladder">
            <div class="panel">
                <h2>HSI CBBC Knock-Out Ladder</h2>
                <div class="chart-wrapper">
                    <iframe class="cbbc-frame" id="cbbc-ladder-frame"
                            srcdoc="{cbbc_srcdoc}"
                            title="HSI CBBC Knock-Out Ladder"></iframe>
                </div>
            </div>
        </section>
        """

    otm_options_html = ""
    otm_sections_html = ""

    if otm_html is not None and otm_html.exists():
        otm_inner_html = otm_html.read_text(encoding="utf-8")
        otm_srcdoc = html_module.escape(otm_inner_html, quote=True)
        otm_options_html = """
                <option value="otm_premium">OtmPremium</option>"""
        otm_sections_html = f"""
        <section class="view hidden" data-view="otm_premium">
            <div class="panel">
                <h2>OtmPremium</h2>
                <div class="chart-wrapper">
                    <iframe class="otm-frame" id="otm-premium-frame"
                            srcdoc="{otm_srcdoc}"
                            title="OtmPremium"></iframe>
                </div>
            </div>
        </section>
        """

    true_range_options_html = ""
    true_range_sections_html = ""
    if true_range_data:
        true_range_options_html = """
                <option value="true_range">True Range</option>"""
        tr_cards = []
        for entry in true_range_data:
            img_uri = png_to_data_uri(entry['image_path'])
            caption = html_module.escape(entry['caption']).replace('\\n', '<br>')
            tr_cards.append(f"""
                <div class="card" style="margin-bottom: 24px; padding: 20px; background: #fff; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.08);">
                    <h3 style="margin-top: 0;">{entry['nice_name']}</h3>
                    <img src="{img_uri}" alt="{entry['nice_name']}" style="width: 100%; height: auto; border-radius: 8px;">
                    <div class="caption-text" style="margin-top: 16px; line-height: 1.5; color: #2c3e50;">{caption}</div>
                </div>
            """)
        
        true_range_sections_html = f"""
        <section class="view hidden" data-view="true_range">
            <div class="panel">
                <h2>True Range Analysis</h2>
                <div class="chart-wrapper" style="max-width: 1000px; margin: 0 auto;">
                    {"".join(tr_cards)}
                </div>
            </div>
        </section>
        """

    trading_time_options_html = ""
    trading_time_sections_html = ""
    if trading_time_data:
        trading_time_options_html = """
                <option value="trading_time">Trading Time</option>"""
        tt_cards = []
        for entry in trading_time_data:
            img_uri = f"data:image/png;base64,{entry['image_base64']}"
            caption = html_module.escape(entry['caption']).replace('\\n', '<br>')
            desc = html_module.escape(entry.get('desc', ''))
            tt_cards.append(f"""
                <div class="card" style="margin-bottom: 24px; padding: 20px; background: #fff; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.08);">
                    <h3 style="margin-top: 0;">{entry['name']}</h3>
                    <p style="font-style: italic; color: #7f8c8d;">{desc}</p>
                    <img src="{img_uri}" alt="{entry['name']}" style="width: 100%; height: auto; border-radius: 8px;">
                    <div class="caption-text" style="margin-top: 16px; line-height: 1.5; color: #2c3e50;">{caption}</div>
                </div>
            """)
        
        trading_time_sections_html = f"""
        <section class="view hidden" data-view="trading_time">
            <div class="panel">
                <h2>Trading Time / Intraday Volatility</h2>
                <div class="chart-wrapper" style="max-width: 1000px; margin: 0 auto;">
                    {"".join(tt_cards)}
                </div>
            </div>
        </section>
        """

    dashboard_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">

    <style>
        :root {{
            color-scheme: light;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }}
        * {{
            box-sizing: border-box;
        }}
        html, body {{
            margin: 0;
            padding: 0;
            width: 100%;
            min-height: 100%;
            background: #f5f6fa;
            color: #1f2430;
        }}
        header {{
            padding: 24px 16px 12px;
            text-align: center;
        }}
        h1 {{
            margin: 0;
            font-size: clamp(24px, 3vw, 34px);
            font-weight: 600;
        }}
        .control-bar {{
            margin: 18px auto 0;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            justify-content: center;
            align-items: center;
        }}
        .control-bar label {{
            font-weight: 600;
        }}
        #view-selector {{
            min-width: 220px;
            padding: 10px 14px;
            border-radius: 8px;
            border: 1px solid #cfd3dc;
            font-size: 15px;
            background: #fff;
            box-shadow: 0 1px 2px rgba(0,0,0,0.08);
        }}
        main {{
            width: 100%;
            max-width: 100%;
            padding: 0 16px 40px;
        }}
        .view {{
            width: 100%;
            max-width: 100%;
            margin: 0 auto;
            overflow-x: auto;
        }}
        .view.hidden {{
            display: none;
        }}
        .panel {{
            background: #fff;
            border-radius: 10px;
            padding: 16px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
            border: 1px solid rgba(15, 23, 42, 0.08);
        }}
        .panel h2 {{
            margin: 0 0 16px;
            text-align: center;
            font-size: 20px;
            font-weight: 600;
        }}
        .chart-wrapper {{
            width: 100%;
            overflow-x: auto;
            padding-bottom: 10px;
        }}
        .chart-wrapper img {{
            display: block;
            width: 100%;
            max-width: none;
            min-width: 900px;
            height: auto;
        }}
        /* Special handling for cards within chart-wrapper */
        .chart-wrapper .card img {{
            min-width: 0; /* Override the global min-width for card images */
        }}
        .caption-text {{
            white-space: pre-wrap; /* Preserve whitespace and line breaks */
            word-wrap: break-word; /* Ensure long words break */
        }}
        .etf-frame {{
            width: 100%;
            min-height: 950px;
            border: none;
            background: #fff;
            overflow: hidden;
        }}
        .cbbc-frame {{
            width: 100%;
            min-height: 900px;
            border: none;
            background: #fff;
            overflow: hidden;
        }}
        .otm-frame {{
            width: 100%;
            min-height: 950px;
            border: none;
            background: #fff;
            overflow: hidden;
        }}
        @media (max-width: 768px) {{
            #view-selector {{
                width: 100%;
            }}
            .panel {{
                padding: 12px;
            }}
            .chart-wrapper img {{
                min-width: 600px;
            }}
            .chart-wrapper .card img {{
                min-width: 0;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="control-bar">
            <label for="view-selector">Select chart:</label>
            <select id="view-selector" aria-label="Select dashboard view">
                <option value="etf">ETF Sector Heatmap</option>
                <option value="hsi">HSI Market Breadth</option>
                <option value="nq">NQ Market Breadth</option>
                <option value="spx">SPX &amp; VIX</option>
                {cbbc_options_html}
                {otm_options_html}
                {true_range_options_html}
                {trading_time_options_html}
            </select>
        </div>
    </header>
    <main>
        <section class="view" data-view="etf">
            <div class="panel">
                <h2>ETF Sector Heatmap</h2>
                <iframe class="etf-frame" srcdoc="{etf_srcdoc}" title="ETF Sector Heatmap"></iframe>
            </div>
        </section>
        <section class="view hidden" data-view="hsi">
            <div class="panel">
                <h2>HSI Market Breadth</h2>
                <div class="chart-wrapper">
                    <img src="{hsi_data_uri}" alt="HSI Market Breadth">
                </div>
            </div>
        </section>
        <section class="view hidden" data-view="nq">
            <div class="panel">
                <h2>NQ Market Breadth</h2>
                <div class="chart-wrapper">
                    <img src="{nq_data_uri}" alt="NQ Market Breadth">
                </div>
            </div>
        </section>
        <section class="view hidden" data-view="spx">
            <div class="panel">
                <h2>SPX &amp; VIX</h2>
                <div class="chart-wrapper">
                    <img src="{spx_data_uri}" alt="SPX &amp; VIX">
                </div>
            </div>
        </section>
        {cbbc_sections_html}
        {otm_sections_html}
        {true_range_sections_html}
        {trading_time_sections_html}
    </main>
    <script>
        (function() {{
            const selector = document.getElementById("view-selector");
            const views = Array.from(document.querySelectorAll(".view"));
            const etfFrame = document.querySelector(".etf-frame");
            const cbbcLadderFrame = document.getElementById("cbbc-ladder-frame");
            const otmFrame = document.getElementById("otm-premium-frame");

            function resizeFrame(frame) {{
                if (!frame || !frame.contentDocument) {{
                    return;
                }}
                const doc = frame.contentDocument;
                const body = doc.body;
                const html = doc.documentElement;
                const height = Math.max(
                    body.scrollHeight,
                    body.offsetHeight,
                    html.clientHeight,
                    html.scrollHeight,
                    html.offsetHeight
                );
                if (height) {{
                    frame.style.height = height + "px";
                }}
            }}

            function updateView(target) {{
                views.forEach((view) => {{
                    view.classList.toggle("hidden", view.dataset.view !== target);
                }});
                if (target === "etf" && etfFrame) {{
                    requestAnimationFrame(() => resizeFrame(etfFrame));
                }} else if (target === "cbbc_ladder" && cbbcLadderFrame) {{
                    requestAnimationFrame(() => resizeFrame(cbbcLadderFrame));
                }} else if (target === "otm_premium" && otmFrame) {{
                    requestAnimationFrame(() => resizeFrame(otmFrame));
                }}
            }}

            selector.addEventListener("change", (event) => {{
                updateView(event.target.value);
            }});

            if (etfFrame) {{
                etfFrame.addEventListener("load", () => {{
                    resizeFrame(etfFrame);
                }});
            }}
            if (cbbcLadderFrame) {{
                cbbcLadderFrame.addEventListener("load", () => {{
                    resizeFrame(cbbcLadderFrame);
                }});
            }}
            if (otmFrame) {{
                otmFrame.addEventListener("load", () => {{
                    resizeFrame(otmFrame);
                }});
            }}

            selector.value = "etf";
            updateView("etf");
        }})();
    </script>
</body>
</html>
"""
    dashboard_file.write_text(dashboard_html, encoding="utf-8")
    return dashboard_file


def format_dashboard_filename(run_time: datetime) -> str:
    """
    Convert a run timestamp into the required dashboard output filename.
    Expected format: Market_DashboardYYYYMMDD_HHMM.html
    """
    target_time = run_time
    if target_time.tzinfo is not None and LOCAL_TZ is not None:
        target_time = target_time.astimezone(LOCAL_TZ)
    return f"Market_Dashboard{target_time.strftime('%Y%m%d_%H%M')}.html"


def run_generation_pipeline(run_time: Optional[datetime] = None) -> Dict[str, Path]:
    """
    Execute the generation pipeline once and return produced asset paths.
    run_time determines the dashboard filename (Market_DashboardYYYYMMDD_HHMM.html).
    """
    effective_time = run_time or current_time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[INFO] Generating ETF sector heatmap...")
    etf_html_path = Path(
        generate_etf_sector_heatmap(
            str(OUTPUT_DIR / "etf_sector_heatmap.html"),
            str(OUTPUT_DIR / "etf_sector_heatmap.xlsx"),
        )
    )
    print(f"[INFO] ETF sector heatmap generated at: {etf_html_path}")

    print("[INFO] Generating HSI market breadth chart...")
    hsi_png_path = Path(generate_market_breadth_hsi(str(OUTPUT_DIR / "market_breadth_hsi.png")))
    print(f"[INFO] HSI market breadth chart generated at: {hsi_png_path}")

    print("[INFO] Generating NQ market breadth chart...")
    nq_png_path = Path(generate_market_breadth_nq(str(OUTPUT_DIR / "market_breadth_nq.png")))
    print(f"[INFO] NQ market breadth chart generated at: {nq_png_path}")

    print("[INFO] Generating SPX vs VIX scatter plot...")
    spx_vix_png_path = Path(generate_spx_vix_chart(str(OUTPUT_DIR / "spx_vix.png")))
    print(f"[INFO] SPX vs VIX chart generated at: {spx_vix_png_path}")

    print("[INFO] Generating HSI CBBC ladder & price detail...")
    cbbc_html_path: Optional[Path] = None
    try:
        CBBC.main()
        cbbc_dir = Path(CBBC.spot_dir)
        html_candidates = sorted(
            cbbc_dir.glob("HSI_CBBC_Ladder_*.html"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if html_candidates:
            cbbc_html_path = html_candidates[0]
            print(f"[INFO] CBBC HTML detected at: {cbbc_html_path}")
        else:
            print("[WARN] No HSI_CBBC_Ladder_*.html found in CBBC spot_dir.")
    except Exception as exc:
        print(f"[WARN] Failed to generate or locate CBBC HTML: {exc}")

    # print("[INFO] Generating OtmPremium dashboard...")
    otm_html_path: Optional[Path] = None
    # try:
    #     otm_html_output = generate_otm_premium_dashboard(
    #         output_html_path=str(OUTPUT_DIR / "otm_premium_dashboard.html")
    #     )
    #     if otm_html_output:
    #         otm_html_path = Path(otm_html_output)
    #         print(f"[INFO] OtmPremium dashboard generated at: {otm_html_path}")
    #     else:
    #         print("[WARN] OtmPremium dashboard was not generated.")
    # except Exception as exc:
    #     print(f"[WARN] Failed to generate OtmPremium dashboard: {exc}")

    print("[INFO] Generating True Range charts...")
    true_range_data = []
    try:
        for ticker, name in Index_day_range.TICKERS.items():
            try:
                # Use mode1 to save locally and get path
                result = Index_day_range.generate_and_send_chart(ticker, name, mode='mode1')
                if result:
                    true_range_data.append(result)
            except Exception as e:
                print(f"[WARN] Error processing True Range for {name}: {e}")
        print(f"[INFO] Generated {len(true_range_data)} True Range charts.")
    except Exception as exc:
        print(f"[WARN] Failed to generate True Range charts: {exc}")

    print("[INFO] Generating Trading Time charts...")
    trading_time_data = []
    try:
        for target in Index_Tradingtime.TARGETS:
            try:
                # Use mode1 with html_sections list
                Index_Tradingtime.plot_intraday_zones(target, mode='mode1', html_sections=trading_time_data)
            except Exception as e:
                print(f"[WARN] Error processing Trading Time for {target['name']}: {e}")
        print(f"[INFO] Generated {len(trading_time_data)} Trading Time charts.")
    except Exception as exc:
        print(f"[WARN] Failed to generate Trading Time charts: {exc}")

    dashboard_filename = format_dashboard_filename(effective_time)
    dashboard_path = build_dashboard_html(
        etf_html_path,
        hsi_png_path,
        nq_png_path,
        spx_vix_png_path,
        OUTPUT_DIR / dashboard_filename,
        cbbc_html_path,
        otm_html_path,
        true_range_data=true_range_data,
        trading_time_data=trading_time_data,
    )
    print(f"[INFO] Dashboard created at: {dashboard_path}")
    try:
        print(f"[INFO] Open in browser: {dashboard_path.resolve().as_uri()}")
    except ValueError:
        # as_uri may fail on Windows UNC paths; fall back to string
        print(f"[INFO] Dashboard path: {dashboard_path.resolve()}")

    return {
        "etf_html": etf_html_path,
        "hsi_png": hsi_png_path,
        "nq_png": nq_png_path,
        "spx_vix_png": spx_vix_png_path,
        "dashboard_html": dashboard_path,
    }


def current_time() -> datetime:
    """
    Return the current time in Asia/Hong_Kong if ZoneInfo is available; otherwise rely on local time.
    Hong Kong does not observe DST, so local time fallback is acceptable if the server already runs in HKT.
    """
    if LOCAL_TZ is not None:
        return datetime.now(LOCAL_TZ)
    return datetime.now()


def get_next_run_datetime(current: datetime) -> datetime:
    """
    Compute the next scheduled run datetime from a reference point.
    Only Monday-Saturday (ISO weekday 1-6) at the configured RUN_TIMES are considered.
    """
    for day_delta in range(0, 8):
        candidate_date = (current + timedelta(days=day_delta)).date()
        if candidate_date.isoweekday() not in ACTIVE_WEEKDAYS:
            continue
        for run_time in RUN_TIMES:
            candidate_dt = datetime.combine(candidate_date, run_time)
            if candidate_dt >= current:
                return candidate_dt
    raise RuntimeError("Unable to determine the next scheduled run within one week.")


def sleep_until(target: datetime) -> None:
    """
    Sleep in small chunks until the target datetime arrives, allowing Ctrl+C to interrupt gracefully.
    """
    while True:
        now = current_time()
        seconds = (target - now).total_seconds()
        if seconds <= 0:
            return
        time.sleep(min(seconds, 60))


def build_multipart_payload(fields: Dict[str, str], files: Dict[str, tuple[str, bytes, str]]) -> tuple[str, bytes]:
    """
    Construct a multipart/form-data payload using only the standard library.
    """
    boundary = f"----TelegramBoundary{uuid.uuid4().hex}"
    lines: list[bytes] = []

    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        lines.append(b"")
        lines.append(value.encode("utf-8"))

    for name, (filename, data, content_type) in files.items():
        lines.append(f"--{boundary}".encode())
        disposition = f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'
        lines.append(disposition.encode())
        lines.append(f"Content-Type: {content_type}".encode())
        lines.append(b"")
        lines.append(data)

    lines.append(f"--{boundary}--".encode())
    lines.append(b"")

    body = b"\r\n".join(lines)
    return f"multipart/form-data; boundary={boundary}", body


def send_telegram_update(
    generated_paths: Dict[str, Path],
    run_time: datetime,
    *,
    raise_on_error: bool = True,
) -> bool:
    """
    Send the freshly generated dashboard HTML file to Telegram with a short status message.
    """
    asset_path = generated_paths["dashboard_html"]
    caption_lines = [
        "📊 Dashboard refreshed",
        f"Completed: {run_time.strftime('%Y-%m-%d %H:%M')} HKT",
        "",
        f"Attachment: {asset_path.name}",
    ]
    caption = "\n".join(caption_lines)
    fields = {"chat_id": str(CHAT_ID), "caption": caption}
    if TOPIC_ID:
        fields["message_thread_id"] = str(TOPIC_ID)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    mime_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
    files = {"document": (asset_path.name, asset_path.read_bytes(), mime_type)}
    content_type, body = build_multipart_payload(fields, files)
    last_exc: Optional[Exception] = None
    for attempt in range(1, TELEGRAM_MAX_SEND_RETRIES + 1):
        request = urllib_request.Request(url, data=body)
        request.add_header("Content-Type", content_type)
        request.add_header("Content-Length", str(len(body)))
        try:
            with urllib_request.urlopen(request, timeout=60) as response:
                response.read()
            print("[INFO] Telegram update sent.")
            return True
        except urllib_error.URLError as exc:
            last_exc = exc
            print(
                f"[WARN] Failed to send Telegram update (attempt {attempt}/{TELEGRAM_MAX_SEND_RETRIES}): {exc}",
                file=sys.stderr,
            )
        except Exception as exc:  # pragma: no cover - unexpected errors
            last_exc = exc
            print(
                f"[WARN] Unexpected error sending Telegram update (attempt {attempt}/{TELEGRAM_MAX_SEND_RETRIES}): {exc}",
                file=sys.stderr,
            )
        if attempt < TELEGRAM_MAX_SEND_RETRIES:
            time.sleep(2)
    if raise_on_error and last_exc is not None:
        raise last_exc
    return False


def run_pipeline_with_retries(
    run_time: datetime,
    *,
    send_telegram: bool,
    max_attempts: int = 10,
    retry_delay_seconds: float = 5.0,
) -> Dict[str, Path]:
    """
    Run the generation pipeline with up to max_attempts retries.
    Optionally send the Telegram update on each successful run.
    """
    attempts = max(1, max_attempts)
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        attempt_label = f"{attempt}/{attempts}"
        print(f"[INFO] Pipeline attempt {attempt_label} starting (send_telegram={send_telegram}).")
        try:
            outputs = run_generation_pipeline(run_time=run_time)
            if send_telegram:
                send_telegram_update(outputs, run_time)
            print(f"[INFO] Pipeline attempt {attempt_label} completed successfully.")
            return outputs
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            last_exc = exc
            print(f"[WARN] Pipeline attempt {attempt_label} failed: {exc}", file=sys.stderr)
            if attempt < attempts:
                if retry_delay_seconds > 0:
                    print(
                        f"[INFO] Retrying in {retry_delay_seconds:.0f} seconds...",
                    )
                    time.sleep(retry_delay_seconds)
                else:
                    print("[INFO] Retrying immediately...")
    error_msg = f"Pipeline failed after {attempts} attempt(s); aborting current trigger."
    print(f"[ERROR] {error_msg}", file=sys.stderr)
    if last_exc is not None:
        raise RuntimeError(error_msg) from last_exc
    raise RuntimeError(error_msg)


def run_schedule_mode() -> None:
    """
    Continuously run the generation pipeline on the prescribed schedule (Mon-Sat @ 09:00, 22:30, 23:30 HKT).
    """
    times_str = ", ".join(run_time.strftime("%H:%M") for run_time in RUN_TIMES)
    print(f"[INFO] Starting scheduled mode (weekdays 1-6 at {times_str} HKT).")
    while True:
        now = current_time()
        next_run = get_next_run_datetime(now)
        minutes_until = max(0.0, (next_run - now).total_seconds() / 60.0)
        print(
            f"[INFO] Next run scheduled for {next_run.strftime('%Y-%m-%d %H:%M')} HKT "
            f"(~{minutes_until:.1f} minutes)."
        )
        try:
            sleep_until(next_run)
        except KeyboardInterrupt:
            print("\n[INFO] Scheduled mode interrupted by user. Exiting.")
            return

        try:
            run_pipeline_with_retries(next_run, send_telegram=True)
        except RuntimeError as exc:
            print(f"[ERROR] Scheduled run failed after retries: {exc}")
            return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate dashboard assets.")
    parser.add_argument(
        "--mode",
        choices=("1", "2"),
        default=DEFAULT_MODE,
        help="1 = single immediate run (default), 2 = scheduled mode (Mon-Sat 09:00/22:30/23:30 HKT)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "1":
        run_pipeline_with_retries(current_time(), send_telegram=False)
    else:
        run_schedule_mode()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Execution interrupted by user.")