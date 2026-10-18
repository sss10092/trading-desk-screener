from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output"
DEX_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"


def scan_crypto(query: str = "SOL", min_liquidity: float = 100_000,
                min_volume_24h: float = 50_000, max_results: int = 10) -> list[dict]:
    try:
        response = requests.get(DEX_SEARCH_URL, params={"q": query}, timeout=25)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"DexScreener request failed: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError("DexScreener returned invalid JSON.") from exc

    rows = []
    for pair in payload.get("pairs") or []:
        try:
            liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
            volume = float((pair.get("volume") or {}).get("h24") or 0)
            price = float(pair.get("priceUsd") or 0)
            created_ms = pair.get("pairCreatedAt")
            age_hours = ((datetime.now(timezone.utc).timestamp() * 1000 - float(created_ms)) / 3_600_000) if created_ms else None
            if liquidity < min_liquidity or volume < min_volume_24h or price <= 0:
                continue
            base = pair.get("baseToken") or {}
            rows.append({
                "chain": pair.get("chainId", ""),
                "dex": pair.get("dexId", ""),
                "symbol": base.get("symbol", ""),
                "name": base.get("name", ""),
                "pair_address": pair.get("pairAddress", ""),
                "price_usd": price,
                "liquidity_usd": liquidity,
                "volume_24h_usd": volume,
                "price_change_24h_pct": (pair.get("priceChange") or {}).get("h24"),
                "age_hours": round(age_hours, 1) if age_hours is not None else None,
                "url": pair.get("url", ""),
            })
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda r: (float(r["volume_24h_usd"]), float(r["liquidity_usd"])), reverse=True)
    rows = rows[:max_results]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"crypto_scan_{query.lower().replace(' ', '_')}.csv"
    if rows:
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        out_path.write_text("No qualifying pairs.\n", encoding="utf-8")
    print(f"DexScreener query={query!r}: {len(rows)} pairs passed filters.")
    print(f"Saved: {out_path}")
    for row in rows:
        change = row["price_change_24h_pct"]
        change_text = f"{float(change):+.2f}%" if change is not None else "n/a"
        print(f"{row['chain']:<12} {row['symbol']:<10} price=${row['price_usd']:.8g} "
              f"24h={change_text:>9} liq=${row['liquidity_usd']:,.0f} vol=${row['volume_24h_usd']:,.0f}")
    print("Screening only: no wallet, exchange, or live order connection exists.")
    return rows
