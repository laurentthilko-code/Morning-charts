#!/usr/bin/env python3
"""
update_graphs.py — regenerates all three investment charts in one shot.
Runs inside GitHub Actions (cloud), independent of any local machine.

This is a straight port of the Mac version (~/Documents/update_graphs.py),
same 3-tier fetch resilience (yfinance Ticker.history -> yfinance download
-> stooq.com CSV) and same status file for diagnosing a bad run.
"""

import os
import sys
import json
import time
import urllib.request
import io
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")  # headless — no display needed
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from matplotlib import rcParams

rcParams["font.family"] = "DejaVu Sans"  # available on GitHub's ubuntu-latest runner

DOCS = os.path.dirname(os.path.abspath(__file__))
STATUS_PATH = os.path.join(DOCS, "status.json")

RUN_STATUS = {
    "run_started": None,
    "run_finished": None,
    "gold_chart": "not_run",
    "uranium_stocks": "not_run",
    "quantum_stocks": "not_run",
    "errors": [],
}

def log(msg):
    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{ts}] {msg}")

STOOQ_MAP = {
    "GC=F": "xauusd",
    "GLD": "gld.us",
    "SLV": "slv.us",
    "GDX": "gdx.us",
    "BTC-USD": "btcusd",
    "^GSPC": "^spx",
    "^STOXX50E": "^stoxx50e",
    "CCJ": "ccj.us",
    "NXE": "nxe.us",
    "UEC": "uec.us",
    "DNN": "dnn.us",
    "IONQ": "ionq.us",
    "RGTI": "rgti.us",
    "QBTS": "qbts.us",
    "QUBT": "qubt.us",
    "EURUSD=X": "eurusd",
}

def fetch_stooq(symbol, start=None, end=None):
    stooq_symbol = STOOQ_MAP.get(symbol)
    if not stooq_symbol:
        return pd.Series(dtype="float64", name=symbol)
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        if not raw or raw.startswith("No data") or "Date,Open" not in raw:
            return pd.Series(dtype="float64", name=symbol)
        df = pd.read_csv(io.StringIO(raw), parse_dates=["Date"])
        df = df.set_index("Date")
        s = df["Close"].copy()
        s.name = symbol
        if start:
            s = s[s.index >= pd.to_datetime(start)]
        if end:
            s = s[s.index <= pd.to_datetime(end)]
        return s
    except Exception as e:
        log(f"  WARNING stooq fallback failed for {symbol}: {e}")
        return pd.Series(dtype="float64", name=symbol)

def fetch_one(symbol, start=None, end=None):
    for attempt in range(2):
        try:
            t = yf.Ticker(symbol)
            df = t.history(start=start, end=end, interval="1d", auto_adjust=True)
            if not df.empty and "Close" in df.columns:
                s = df["Close"].copy()
                if isinstance(s, pd.DataFrame):
                    s = s.squeeze()
                s.name = symbol
                if hasattr(s.index, "tz") and s.index.tz is not None:
                    s.index = s.index.tz_localize(None)
                return s
            break
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            log(f"  WARNING Ticker.history() failed for {symbol}: {e}")

    for attempt in range(2):
        try:
            df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False, interval="1d")
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    s = df["Close"].copy()
                    if isinstance(s, pd.DataFrame):
                        s = s.squeeze()
                else:
                    if "Close" not in df.columns and "Adj Close" in df.columns:
                        df = df.rename(columns={"Adj Close": "Close"})
                    s = df["Close"].copy()
                s.name = symbol
                if hasattr(s.index, "tz") and s.index.tz is not None:
                    s.index = s.index.tz_localize(None)
                return s
            break
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            log(f"  WARNING yf.download() also failed for {symbol}: {e}")

    s = fetch_stooq(symbol, start, end)
    if not s.empty:
        log(f"  -> {symbol} recovered via stooq fallback")
        return s

    log(f"  FAILED all sources failed for {symbol}")
    return pd.Series(dtype="float64", name=symbol)

def join_series(series_list):
    return pd.concat(series_list, axis=1, join="outer").dropna(axis=1, how="all")

def normalize_to_date(df, base_date):
    base_ts = pd.to_datetime(base_date)
    if base_ts not in df.index:
        after = df.loc[df.index >= base_ts]
        if after.empty:
            return pd.DataFrame(index=df.index)
        base_ts = after.index[0]
    norm = pd.DataFrame(index=df.index)
    for c in df.columns:
        base = df.loc[base_ts, c]
        if not pd.isna(base):
            norm[c] = 100.0 * df[c] / base
    return norm.dropna(axis=1, how="all")

def save_plot(df, labels, outfile, title, highlight=None):
    plt.figure(figsize=(12, 7))
    for col in df.columns:
        lw = 3.0 if col == highlight else 1.4
        color = "black" if col == highlight else None
        plt.plot(df.index, df[col], label=labels.get(col, col), linewidth=lw,
                 **({} if color is None else {"color": color}))
    plt.title(title, fontsize=13)
    plt.xlabel("Date")
    plt.ylabel("Index (100 = base date)")
    plt.grid(True, alpha=0.4)
    plt.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(outfile, dpi=150)
    plt.close()
    log(f"  OK {os.path.basename(outfile)}")

def update_gold():
    log("Updating gold chart...")
    SYMBOLS = ["GC=F", "GLD", "SLV", "GDX", "BTC-USD", "^GSPC", "^STOXX50E"]
    USD_SYMBOLS = {"GC=F", "GLD", "SLV", "GDX", "BTC-USD", "^GSPC"}
    LABELS = {
        "GC=F": "Gold (EUR)", "GLD": "Gold ETF (GLD, EUR)", "SLV": "Silver (EUR)",
        "GDX": "Gold Miners (EUR)", "BTC-USD": "Bitcoin (EUR)",
        "^GSPC": "S&P 500 (EUR)", "^STOXX50E": "Euro Stoxx 50 (EUR)",
    }
    BASE = "2024-12-31"
    START = "2024-12-01"

    series_list = [fetch_one(s, START) for s in SYMBOLS]
    prices = join_series(series_list)

    if prices.empty or not isinstance(prices.index, pd.DatetimeIndex):
        log("  FAILED no price data retrieved for gold chart - skipping.")
        RUN_STATUS["gold_chart"] = "failed_no_data"
        RUN_STATUS["errors"].append("gold_chart: no data from any source")
        return

    eurusd = fetch_one("EURUSD=X", prices.index.min().strftime("%Y-%m-%d"),
                       prices.index.max().strftime("%Y-%m-%d"))
    eurusd = eurusd.asfreq("B").ffill().reindex(prices.index).ffill()
    for c in prices.columns:
        if c in USD_SYMBOLS:
            prices[c] = prices[c].div(eurusd)

    prices = prices[prices.index >= pd.to_datetime(BASE)]
    norm = normalize_to_date(prices, BASE)
    ORDER = ["GC=F", "GLD", "SLV", "GDX", "^GSPC", "^STOXX50E", "BTC-USD"]
    norm = norm[[c for c in ORDER if c in norm.columns]]

    save_plot(norm, LABELS, os.path.join(DOCS, "gold_chart.png"),
              f"Gold vs Gold Assets (EUR) - normalized to 100 on {BASE}", highlight="GC=F")
    RUN_STATUS["gold_chart"] = "ok"

def update_uranium_quantum():
    log("Updating uranium & quantum charts...")
    BASE = "2024-12-31"
    START = "2024-12-01"

    groups = [
        (["CCJ", "NXE", "UEC", "DNN"],
         {"CCJ": "Cameco (CCJ)", "NXE": "NexGen (NXE)",
          "UEC": "Uranium Energy (UEC)", "DNN": "Denison Mines (DNN)"},
         "uranium_stocks.png", "uranium_stocks",
         f"Uranium pure plays - Index 100 on {BASE}"),
        (["IONQ", "RGTI", "QBTS", "QUBT"],
         {"IONQ": "IonQ (IONQ)", "RGTI": "Rigetti (RGTI)",
          "QBTS": "D-Wave (QBTS)", "QUBT": "Quantum Computing (QUBT)"},
         "quantum_stocks.png", "quantum_stocks",
         f"Quantum pure plays - Index 100 on {BASE}"),
    ]

    for symbols, labels, filename, status_key, title in groups:
        series_list = [fetch_one(s, START) for s in symbols]
        prices = join_series(series_list)
        if prices.empty:
            log(f"  WARNING no data for {filename}")
            RUN_STATUS[status_key] = "failed_no_data"
            RUN_STATUS["errors"].append(f"{filename}: no data from any source")
            continue
        prices = prices[prices.index >= pd.to_datetime(BASE)]
        norm = normalize_to_date(prices, BASE)
        norm = norm[[s for s in symbols if s in norm.columns]]
        save_plot(norm, labels, os.path.join(DOCS, filename), title)
        RUN_STATUS[status_key] = "ok"

if __name__ == "__main__":
    RUN_STATUS["run_started"] = datetime.now(timezone.utc).isoformat()
    log("Refreshing all investment charts...")
    exit_code = 0
    try:
        update_gold()
        update_uranium_quantum()
        if RUN_STATUS["errors"]:
            log("Run finished with partial failures - see errors above.")
        else:
            log("All charts updated.")
    except Exception as e:
        log(f"FATAL error: {e}")
        RUN_STATUS["errors"].append(f"fatal: {e}")
        exit_code = 1
    finally:
        RUN_STATUS["run_finished"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(STATUS_PATH, "w") as f:
                json.dump(RUN_STATUS, f, indent=2)
        except Exception as e:
            log(f"  WARNING could not write status file: {e}")
    sys.exit(exit_code)
