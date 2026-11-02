"""Exchange rates (per 1 US dollar), refreshed twice a day, with an offline fallback."""

import json
import threading
import time
from datetime import datetime

from jobslop import net
from jobslop.config import DATA_DIR

# ---- exchange rates (per 1 US dollar), refreshed twice a day, with offline fallback
RATES_FILE = DATA_DIR / "rates.json"
FALLBACK_RATES = {"USD": 1, "GBP": 0.75, "EUR": 0.9, "CAD": 1.38, "AUD": 1.52, "NZD": 1.66, "INR": 95, "JPY": 157,
                  "CHF": 0.8, "SEK": 10.3, "NOK": 10.6, "DKK": 6.7, "PLN": 3.8, "CZK": 22.5, "HUF": 355, "RON": 4.5,
                  "ZAR": 17.5, "SGD": 1.3, "HKD": 7.8, "AED": 3.67, "SAR": 3.75, "QAR": 3.64, "BRL": 5.5, "MXN": 18.5,
                  "TRY": 41, "ILS": 3.6, "MYR": 4.3, "PHP": 57, "IDR": 16000, "THB": 33, "VND": 26000, "KRW": 1380,
                  "UAH": 41, "EGP": 49, "NGN": 1500, "ARS": 1300, "CLP": 940, "COP": 4000}
rates_lock = threading.Lock()


def get_rates():
    with rates_lock:
        try:
            cached = json.loads(RATES_FILE.read_text(encoding="utf-8"))
            if time.time() - cached["t"] < 12 * 3600:
                return cached
        except Exception:
            cached = None
        for url, key in (("https://open.er-api.com/v6/latest/USD", "rates"),
                         ("https://api.frankfurter.app/latest?from=USD", "rates")):
            try:
                rates = net.get_json(url, timeout=10)[key]
                rates["USD"] = 1
                data = {"t": time.time(), "rates": rates, "source": url.split("/")[2],
                        "updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
                RATES_FILE.write_text(json.dumps(data), encoding="utf-8")
                return data
            except Exception:
                continue
        return cached or {"t": 0, "rates": FALLBACK_RATES, "source": "built-in (offline)", "updated": "approximate"}
