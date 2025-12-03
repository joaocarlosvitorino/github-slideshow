import csv
import json
import math
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
except Exception:  # noqa: BLE001
    RandomForestRegressor = None
    mean_absolute_error = None
    mean_squared_error = None
    r2_score = None


PERIOD_TO_RANGE = {
    "1m": "1mo",
    "3m": "3mo",
    "6m": "6mo",
    "1y": "1y",
    "2y": "2y",
    "5y": "5y",
}

POPULAR_BY_SECTOR = {
    "Energia": ["PETR4", "PRIO3", "RAIZ4"],
    "Financeiro": ["ITUB4", "BBDC4", "BBAS3"],
    "Varejo": ["MGLU3", "VIIA3", "LREN3"],
    "Siderurgia": ["VALE3", "USIM5", "CSNA3"],
    "Tecnologia": ["LWSA3", "POSI3", "TOTS3"],
}


class TickerError(Exception):
    """Custom error to describe ticker retrieval problems."""


def to_date(timestamp: int) -> str:
    return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")


def _friendly_error_message(exc: Exception) -> str:
    reason = getattr(exc, "reason", "")
    details = str(reason or exc)
    if "403" in details:
        return "A requisição foi bloqueada (403). Verifique VPN/proxy e acesso à Yahoo Finance."
    if "timed out" in details.lower():
        return "Tempo esgotado ao contactar o provedor de dados. Confira sua conexão."
    return details or "Erro de rede desconhecido"


def fetch_json(urls):
    if isinstance(urls, str):
        urls = [urls]
    errors = []
    for url in urls:
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request) as response:
                body = response.read()
            return json.loads(body.decode("utf-8"))
        except (HTTPError, URLError, OSError) as exc:
            errors.append(_friendly_error_message(exc))
            continue
    combined = "; ".join(errors) or "Falha ao recuperar dados do ticker"
    raise TickerError(combined)


def fetch_ticker_series(ticker: str, period: str):
    try:
        return _fetch_yahoo_series(ticker, period)
    except TickerError as err:
        detail = str(err).lower()
        if "403" in detail or "401" in detail or "unauthorized" in detail:
            return _fetch_stooq_series(ticker, period)
        raise


def _fetch_yahoo_series(ticker: str, period: str):
    range_value = PERIOD_TO_RANGE.get(period, "6mo")
    base = f"{ticker}.SA?range={range_value}&interval=1d&events=history&includeAdjustedClose=true"
    urls = [
        f"https://query2.finance.yahoo.com/v8/finance/chart/{base}",
        f"https://query1.finance.yahoo.com/v8/finance/chart/{base}",
    ]
    payload = fetch_json(urls)
    result = payload.get("chart", {}).get("result", [])
    if not result:
        error_message = payload.get("chart", {}).get("error", {}).get("description")
        raise TickerError(error_message or "Dados indisponíveis para este ticker")

    record = result[0]
    timestamps = record.get("timestamp", [])
    quote = (record.get("indicators", {}) or {}).get("quote", [{}])[0]
    closes = quote.get("close", [])
    highs = quote.get("high", [])
    lows = quote.get("low", [])
    opens = quote.get("open", [])
    volumes = quote.get("volume", [])

    series = []
    for idx, timestamp in enumerate(timestamps):
        close = closes[idx] if idx < len(closes) else None
        high = highs[idx] if idx < len(highs) else None
        low = lows[idx] if idx < len(lows) else None
        open_ = opens[idx] if idx < len(opens) else None
        volume = volumes[idx] if idx < len(volumes) else 0
        if close is None or math.isnan(close) or close <= 0:
            continue
        series.append(
            {
                "date": to_date(timestamp),
                "open": float(open_ or close),
                "high": float(high or close),
                "low": float(low or close),
                "close": float(close),
                "volume": int(volume or 0),
            }
        )
    return series


def _fetch_stooq_series(ticker: str, period: str):
    # Stooq offers an open CSV without authentication, suitable when Yahoo blocks requests.
    url = f"https://stooq.pl/q/d/l/?s={ticker.lower()}.sa&i=d"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request) as response:
            content = response.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise TickerError(_friendly_error_message(exc))

    lines = [line for line in content.splitlines() if line.strip()][1:]
    if not lines:
        raise TickerError("Dados indisponíveis para este ticker (fallback Stooq)")

    def should_keep(date_str: str) -> bool:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return False
        today = datetime.utcnow().date()
        days_map = {"1m": 32, "3m": 100, "6m": 190, "1y": 370, "2y": 740, "5y": 1900}
        limit_days = days_map.get(period, 190)
        return (today - date_obj).days <= limit_days

    series = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        date_str, open_, high, low, close, volume = parts[:6]
        if not should_keep(date_str):
            continue
        try:
            close_f = float(close)
            if close_f <= 0:
                continue
            series.append(
                {
                    "date": date_str,
                    "open": float(open_ or close_f),
                    "high": float(high or close_f),
                    "low": float(low or close_f),
                    "close": close_f,
                    "volume": int(volume or 0),
                }
            )
        except ValueError:
            continue

    if not series:
        raise TickerError("Dados indisponíveis (fallback Stooq)")
    return series


def fetch_fundamentals(ticker: str):
    try:
        suffix = f"{ticker}.SA?modules=financialData,defaultKeyStatistics,summaryProfile"
        urls = [
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{suffix}",
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{suffix}",
        ]
        payload = fetch_json(urls)
        result = payload.get("quoteSummary", {}).get("result", [])
        if not result:
            raise TickerError("Fundamentais indisponíveis no Yahoo")
        data = result[0]
        financial = data.get("financialData", {})
        stats = data.get("defaultKeyStatistics", {})
        profile = data.get("summaryProfile", {})
    except TickerError as err:
        detail = str(err).lower()
        if "403" in detail or "401" in detail or "unauthorized" in detail:
            return _fetch_brapi_fundamentals(ticker)
        return {}

    def safe_get(container, key):
        value = container.get(key)
        if isinstance(value, dict):
            return value.get("fmt") or value.get("raw")
        return value

    return {
        "pe": safe_get(stats, "forwardPE"),
        "eps": safe_get(stats, "trailingEps"),
        "market_cap": safe_get(stats, "marketCap"),
        "beta": safe_get(stats, "beta"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "debt_to_equity": safe_get(financial, "debtToEquity"),
        "profit_margin": safe_get(financial, "profitMargins"),
        "recommendation": safe_get(financial, "recommendationKey"),
    }


def _fetch_brapi_fundamentals(ticker: str):
    # Public brapi.dev endpoint that usually works without an API key for light usage.
    url = f"https://brapi.dev/api/quote/{ticker}?modules=summaryProfile,financialData,defaultKeyStatistics"
    try:
        payload = fetch_json(url)
    except TickerError:
        return {}

    results = payload.get("results", [])
    if not results:
        return {}
    data = results[0]
    return {
        "pe": data.get("forwardPE") or data.get("priceEarnings"),
        "eps": data.get("epsTrailingTwelveMonths") or data.get("trailingEps"),
        "market_cap": data.get("marketCap"),
        "beta": data.get("beta"),
        "sector": data.get("sector"),
        "industry": data.get("industry"),
        "debt_to_equity": data.get("debtToEquity") or data.get("totalDebt"),
        "profit_margin": data.get("profitMargins") or data.get("profit") or data.get("grossMargins"),
        "recommendation": data.get("recommendationKey") or data.get("recommendation"),
    }


def calculate_sma(values, length):
    sma = []
    for idx in range(len(values)):
        if idx + 1 < length:
            sma.append(None)
            continue
        window = values[idx + 1 - length : idx + 1]
        sma.append(sum(window) / length)
    return sma


def calculate_ema(values, length):
    if not values:
        return []
    k = 2 / (length + 1)
    ema = [values[0]]
    for price in values[1:]:
        ema.append((price * k) + (ema[-1] * (1 - k)))
    return ema


def calculate_rsi(values, length=14):
    if len(values) < length + 1:
        return []
    gains = []
    losses = []
    for idx in range(1, len(values)):
        delta = values[idx] - values[idx - 1]
        gains.append(delta if delta > 0 else 0)
        losses.append(-delta if delta < 0 else 0)

    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length
    rsi_values = [None] * length
    rs = avg_gain / avg_loss if avg_loss else 100
    rsi_values.append(100 - 100 / (1 + rs))

    for idx in range(length, len(gains)):
        gain = gains[idx]
        loss = losses[idx]
        avg_gain = ((avg_gain * (length - 1)) + gain) / length
        avg_loss = ((avg_loss * (length - 1)) + loss) / length
        rs = avg_gain / avg_loss if avg_loss else 100
        rsi_values.append(100 - 100 / (1 + rs))
    return rsi_values


def macd(values):
    ema12 = calculate_ema(values, 12)
    ema26 = calculate_ema(values, 26)
    macd_line = []
    for i in range(len(values)):
        if i < len(ema12) and i < len(ema26):
            macd_line.append(ema12[i] - ema26[i])
        else:
            macd_line.append(None)
    signal = calculate_ema([v for v in macd_line if v is not None], 9)
    histogram = []
    sig_idx = 0
    for v in macd_line:
        if v is None or sig_idx >= len(signal):
            histogram.append(None)
        else:
            histogram.append(v - signal[sig_idx])
            sig_idx += 1
    return macd_line, signal, histogram


def bollinger(values, length=20, num_std=2):
    upper = []
    lower = []
    mid = calculate_sma(values, length)
    for idx in range(len(values)):
        if idx + 1 < length:
            upper.append(None)
            lower.append(None)
            continue
        window = values[idx + 1 - length : idx + 1]
        mean = sum(window) / length
        variance = sum((v - mean) ** 2 for v in window) / length
        std = math.sqrt(variance)
        upper.append(mean + num_std * std)
        lower.append(mean - num_std * std)
    return mid, upper, lower


def annualized_volatility(returns):
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance) * math.sqrt(252)


def sharpe_ratio(returns, risk_free=0.04):
    if not returns:
        return 0.0
    daily_rf = (1 + risk_free) ** (1 / 252) - 1
    excess = [r - daily_rf for r in returns]
    vol = annualized_volatility(excess)
    if vol == 0:
        return 0.0
    avg = sum(excess) / len(excess)
    return (avg * 252) / vol


def distribution(returns, bins=5):
    if not returns:
        return []
    mn, mx = min(returns), max(returns)
    if mn == mx:
        return [(mn, mx, len(returns))]
    step = (mx - mn) / bins
    dist = []
    for i in range(bins):
        lower = mn + i * step
        upper = lower + step
        count = len([r for r in returns if lower <= r < upper])
        dist.append((lower, upper, count))
    dist[-1] = (dist[-1][0], dist[-1][1], len([r for r in returns if r >= dist[-1][0]]))
    return dist


def correlation_matrix(series_map):
    tickers = list(series_map.keys())
    returns_map = {}
    for ticker, series in series_map.items():
        closes = [p["close"] for p in series]
        daily = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
        returns_map[ticker] = daily

    matrix = {}
    for i, t1 in enumerate(tickers):
        row = {}
        for j, t2 in enumerate(tickers):
            if i == j:
                row[t2] = 1.0
                continue
            a = returns_map[t1]
            b = returns_map[t2]
            length = min(len(a), len(b))
            if length == 0:
                row[t2] = 0.0
                continue
            mean_a = sum(a[:length]) / length
            mean_b = sum(b[:length]) / length
            cov = sum((a[k] - mean_a) * (b[k] - mean_b) for k in range(length)) / length
            std_a = math.sqrt(sum((a[k] - mean_a) ** 2 for k in range(length)) / length)
            std_b = math.sqrt(sum((b[k] - mean_b) ** 2 for k in range(length)) / length)
            row[t2] = cov / (std_a * std_b) if std_a and std_b else 0.0
        matrix[t1] = row
    return matrix


def normalized_performance(series):
    if not series:
        return []
    base = series[0]["close"]
    return [(p["date"], (p["close"] / base) - 1) for p in series]


def forecast_random_forest(series, horizon=30):
    if RandomForestRegressor is None:
        return None
    closes = [p["close"] for p in series]
    if len(closes) < 40:
        return None
    X, y = [], []
    window = 5
    for idx in range(window, len(closes)):
        X.append(closes[idx - window : idx])
        y.append(closes[idx])
    model = RandomForestRegressor(n_estimators=200, random_state=42)
    model.fit(X, y)

    preds = []
    history = closes[-window:]
    for _ in range(horizon):
        next_price = model.predict([history])[-1]
        preds.append(next_price)
        history = history[1:] + [next_price]

    actual = closes[-horizon:] if len(closes) >= horizon else closes
    metrics = {}
    if actual and len(actual) == horizon and mean_absolute_error:
        metrics = {
            "mae": float(mean_absolute_error(actual, preds[: len(actual)])),
            "rmse": float(math.sqrt(mean_squared_error(actual, preds[: len(actual)]))),
            "r2": float(r2_score(actual, preds[: len(actual)])),
        }
    else:
        metrics = {"mae": None, "rmse": None, "r2": None}

    base_date = datetime.strptime(series[-1]["date"], "%Y-%m-%d")
    forecasted = [
        {
            "date": (base_date + timedelta(days=idx + 1)).strftime("%Y-%m-%d"),
            "predicted": preds[idx],
            "actual": actual[idx] if idx < len(actual) else None,
        }
        for idx in range(len(preds))
    ]
    return {"forecast": forecasted, "metrics": metrics, "feature_importance": getattr(model, "feature_importances_", [])}


class TickerAnalyzerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("B3 Ticker Analyzer - Desktop")
        self.master.configure(bg="#0f172a")
        self.ticker_var = tk.StringVar(value="PETR4")
        self.period_var = tk.StringVar(value="6m")
        self.compare_var = tk.StringVar(value="PETR4,VALE3,ITUB4")
        self.status_var = tk.StringVar(value="Pronto para analisar.")
        self.loading = False
        self.latest_series = {}
        self.latest_indicators = {}
        self.latest_forecast = {}
        self._setup_style()
        self._build_ui()

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0f172a")
        style.configure("TLabel", background="#0f172a", foreground="#e2e8f0")
        style.configure("TButton", background="#1e293b", foreground="#e2e8f0", padding=6)
        style.map("TButton", background=[("active", "#334155")])
        style.configure("TLabelframe", background="#0f172a", foreground="#e2e8f0")
        style.configure("TLabelframe.Label", background="#0f172a", foreground="#e2e8f0")
        style.configure("Treeview", background="#0b1220", foreground="#e2e8f0", fieldbackground="#0b1220")
        style.configure("Horizontal.TProgressbar", troughcolor="#1f2937", background="#22d3ee", bordercolor="#1f2937")

    def _build_ui(self):
        root = ttk.Frame(self.master, padding=14)
        root.grid(row=0, column=0, sticky="nsew")
        self.master.rowconfigure(0, weight=1)
        self.master.columnconfigure(0, weight=1)

        # Top controls
        control = ttk.Frame(root)
        control.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        control.columnconfigure(6, weight=1)

        ttk.Label(control, text="Ticker principal:").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(control, textvariable=self.ticker_var, width=10)
        entry.grid(row=0, column=1, padx=6)
        entry.bind("<Return>", lambda _e: self.start_analyze())

        ttk.Label(control, text="Período:").grid(row=0, column=2)
        period_box = ttk.Combobox(control, textvariable=self.period_var, values=list(PERIOD_TO_RANGE.keys()), width=5)
        period_box.grid(row=0, column=3, padx=6)

        analyze_btn = ttk.Button(control, text="Analisar", command=self.start_analyze)
        analyze_btn.grid(row=0, column=4, padx=6)

        ttk.Button(control, text="Exportar CSV", command=self.export_csv).grid(row=0, column=5, padx=6)

        ttk.Label(control, text="Comparar (até 10, separados por vírgula):").grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        compare_entry = ttk.Entry(control, textvariable=self.compare_var, width=40)
        compare_entry.grid(row=1, column=3, columnspan=3, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(control, text="Comparar", command=self.start_compare).grid(row=1, column=6, sticky="e", padx=6, pady=(8, 0))

        ttk.Label(control, text="Tickers populares:").grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 4))
        popular_frame = ttk.Frame(control)
        popular_frame.grid(row=3, column=0, columnspan=7, sticky="ew")
        col = 0
        for sector, tickers in POPULAR_BY_SECTOR.items():
            box = ttk.Labelframe(popular_frame, text=sector)
            box.grid(row=0, column=col, padx=4, sticky="ew")
            for t in tickers:
                ttk.Button(box, text=t, command=lambda tv=t: self._set_ticker(tv)).pack(side="left", padx=2, pady=2)
            col += 1

        # Notebook
        self.notebook = ttk.Notebook(root)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        root.rowconfigure(1, weight=1)

        self.price_tab = ttk.Frame(self.notebook)
        self.indicators_tab = ttk.Frame(self.notebook)
        self.analysis_tab = ttk.Frame(self.notebook)
        self.compare_tab = ttk.Frame(self.notebook)
        self.forecast_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.price_tab, text="Preço")
        self.notebook.add(self.indicators_tab, text="Indicadores")
        self.notebook.add(self.analysis_tab, text="Análise Completa")
        self.notebook.add(self.compare_tab, text="Comparação")
        self.notebook.add(self.forecast_tab, text="Previsão ML")

        for tab in [self.price_tab, self.indicators_tab, self.analysis_tab, self.compare_tab, self.forecast_tab]:
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)

        self.price_text = self._make_text(self.price_tab)
        self.indicators_text = self._make_text(self.indicators_tab)
        self.analysis_text = self._make_text(self.analysis_tab)
        self.compare_text = self._make_text(self.compare_tab)
        self.forecast_text = self._make_text(self.forecast_tab)

        # Status bar
        status_bar = ttk.Frame(root)
        status_bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        status_bar.columnconfigure(1, weight=1)
        self.progress = ttk.Progressbar(status_bar, mode="indeterminate", length=160, style="Horizontal.TProgressbar")
        self.progress.grid(row=0, column=0, padx=(0, 8))
        self.status_label = ttk.Label(status_bar, textvariable=self.status_var)
        self.status_label.grid(row=0, column=1, sticky="w")

    def _fmt(self, value, decimals=2):
        if value is None:
            return "--"
        return f"{value:.{decimals}f}"

    def _make_text(self, parent):
        text = tk.Text(parent, height=20, background="#0b1220", foreground="#e2e8f0", insertbackground="#22d3ee")
        text.grid(row=0, column=0, sticky="nsew")
        text.configure(state="disabled")
        return text

    def _set_ticker(self, ticker):
        self.ticker_var.set(ticker)
        self.start_analyze()

    def _set_loading(self, loading: bool, message: str = ""):
        self.loading = loading
        if loading:
            self.progress.start(12)
        else:
            self.progress.stop()
        if message:
            self.status_var.set(message)

    def start_analyze(self):
        if self.loading:
            return
        ticker = self.ticker_var.get().strip().upper()
        period = self.period_var.get()
        if not ticker:
            messagebox.showwarning("Ticker inválido", "Informe um ticker, como PETR4")
            return
        self._set_loading(True, "Carregando dados e indicadores...")
        threading.Thread(target=self._load_ticker, args=(ticker, period), daemon=True).start()

    def _load_ticker(self, ticker: str, period: str):
        try:
            series = fetch_ticker_series(ticker, period)
            fundamentals = fetch_fundamentals(ticker)
            closes = [p["close"] for p in series]
            sma20 = calculate_sma(closes, 20)
            sma50 = calculate_sma(closes, 50)
            sma200 = calculate_sma(closes, 200)
            rsi = calculate_rsi(closes, 14)
            macd_line, macd_signal, macd_hist = macd(closes)
            mid, upper, lower = bollinger(closes)
            returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
            vol = annualized_volatility(returns)
            sharpe = sharpe_ratio(returns)
            dist = distribution(returns, bins=8)
            perf = normalized_performance(series)
            forecast = forecast_random_forest(series)

            indicators = {
                "sma20": sma20[-1] if len(sma20) else None,
                "sma50": sma50[-1] if len(sma50) else None,
                "sma200": sma200[-1] if len(sma200) else None,
                "rsi": rsi[-1] if len(rsi) else None,
                "macd": macd_line[-1] if len(macd_line) else None,
                "macd_signal": macd_signal[-1] if len(macd_signal) else None,
                "macd_hist": macd_hist[-1] if len(macd_hist) else None,
                "boll_mid": mid[-1] if len(mid) else None,
                "boll_upper": upper[-1] if len(upper) else None,
                "boll_lower": lower[-1] if len(lower) else None,
                "volatility": vol,
                "sharpe": sharpe,
                "distribution": dist,
                "performance": perf,
            }

            self.latest_series = {ticker: series}
            self.latest_indicators = {ticker: indicators}
            self.latest_forecast = {ticker: forecast}
            self.master.after(0, self._render_result, ticker, period, series, indicators, fundamentals, forecast)
        except TickerError as err:
            self.master.after(0, self._show_error, str(err))
        except Exception as exc:  # noqa: BLE001
            self.master.after(0, self._show_error, f"Erro inesperado: {exc}")

    def _show_error(self, message: str):
        self._set_loading(False, message)
        messagebox.showerror("Erro", message)

    def _render_result(self, ticker, period, series, indicators, fundamentals, forecast):
        self._set_loading(False, f"{ticker}.SA carregado para {period}.")
        if not series:
            return
        self._fill_price_tab(ticker, period, series, indicators)
        self._fill_indicators_tab(indicators)
        self._fill_analysis_tab(ticker, fundamentals, indicators)
        self._fill_forecast_tab(ticker, forecast)
        self.notebook.select(self.price_tab)

    def _fill_price_tab(self, ticker, period, series, indicators):
        text = self.price_text
        text.configure(state="normal")
        text.delete("1.0", tk.END)
        closes = [p["close"] for p in series]
        latest = series[-1]
        change = latest["close"] - series[0]["close"]
        change_pct = (change / series[0]["close"]) * 100
        text.insert(tk.END, f"Ticker: {ticker}.SA\n")
        text.insert(tk.END, f"Período: {period}\n")
        text.insert(tk.END, f"Último preço: R$ {latest['close']:.2f}\n")
        text.insert(tk.END, f"Variação: {change:+.2f} ({change_pct:+.2f}%)\n")
        text.insert(tk.END, f"Volume: {latest['volume']}\n")
        text.insert(
            tk.END,
            "SMA 20/50/200: "
            f"{self._fmt(indicators['sma20'])} | {self._fmt(indicators['sma50'])} | {self._fmt(indicators['sma200'])}\n",
        )
        text.insert(
            tk.END,
            "Bandas de Bollinger (20): "
            f"{self._fmt(indicators['boll_lower'])} - {self._fmt(indicators['boll_mid'])} - {self._fmt(indicators['boll_upper'])}\n\n",
        )
        text.insert(tk.END, "Últimas 15 observações (preço, volume):\n")
        for row in series[-15:]:
            text.insert(
                tk.END,
                f"{row['date']}: R$ {row['close']:.2f} | Vol {row['volume']}\n",
            )
        text.configure(state="disabled")

    def _fill_indicators_tab(self, indicators):
        text = self.indicators_text
        text.configure(state="normal")
        text.delete("1.0", tk.END)
        text.insert(tk.END, "Indicadores Técnicos\n")
        text.insert(tk.END, f"RSI (14): {self._fmt(indicators['rsi'])}\n")
        text.insert(
            tk.END,
            "MACD: "
            f"{self._fmt(indicators['macd'], 4)} | Sinal: {self._fmt(indicators['macd_signal'], 4)} | "
            f"Hist: {self._fmt(indicators['macd_hist'], 4)}\n",
        )
        text.insert(tk.END, f"Volatilidade anualizada: {indicators['volatility']*100:.2f}%\n")
        text.insert(tk.END, f"Sharpe Ratio: {indicators['sharpe']:.2f}\n\n")

        text.insert(tk.END, "Distribuição de retornos diários:\n")
        for lower, upper, count in indicators.get("distribution", []):
            text.insert(tk.END, f"{lower*100:>6.2f}% a {upper*100:>6.2f}%: {count}\n")

        text.insert(tk.END, "\nDesempenho normalizado (últimos 10 pts):\n")
        for date, perf in indicators.get("performance", [])[-10:]:
            text.insert(tk.END, f"{date}: {perf*100:+.2f}%\n")
        text.configure(state="disabled")

    def _fill_analysis_tab(self, ticker, fundamentals, indicators):
        text = self.analysis_text
        text.configure(state="normal")
        text.delete("1.0", tk.END)
        text.insert(tk.END, "Análise Completa\n")
        text.insert(tk.END, "Fundamentalista:\n")
        text.insert(tk.END, f"Setor/Indústria: {fundamentals.get('sector','--')} / {fundamentals.get('industry','--')}\n")
        text.insert(tk.END, f"P/L: {fundamentals.get('pe','--')} | EPS: {fundamentals.get('eps','--')}\n")
        text.insert(tk.END, f"Margem: {fundamentals.get('profit_margin','--')} | Dívida/Patrimônio: {fundamentals.get('debt_to_equity','--')}\n")
        text.insert(tk.END, f"Market Cap: {fundamentals.get('market_cap','--')} | Beta: {fundamentals.get('beta','--')}\n")
        text.insert(tk.END, f"Recomendação: {fundamentals.get('recommendation','--')}\n\n")

        text.insert(tk.END, "Técnico:\n")
        text.insert(tk.END, f"RSI sugere: {'Sobrevendido' if indicators.get('rsi') and indicators['rsi'] < 30 else 'Neutro/Sobrecomprado'}\n")
        text.insert(
            tk.END,
            "Tendência médias: "
            f"{self._trend_text(indicators.get('sma20'), indicators.get('sma50'), indicators.get('sma200'))}\n",
        )
        text.insert(tk.END, f"Volatilidade/Sharpe: {indicators.get('volatility',0)*100:.2f}% / {indicators.get('sharpe',0):.2f}\n")
        text.insert(tk.END, "Bollinger posição: ")
        if indicators.get("boll_upper") and indicators.get("boll_lower"):
            text.insert(
                tk.END,
                f"{self._boll_position(indicators)}\n",
            )
        else:
            text.insert(tk.END, "--\n")

        text.insert(tk.END, "\nRecomendações automáticas:\n")
        recs = []
        if indicators.get("rsi") and indicators["rsi"] < 30:
            recs.append("Momentum de recuperação possível (RSI < 30)")
        if indicators.get("macd_hist") and indicators["macd_hist"] > 0:
            recs.append("MACD sugere cruzamento de alta")
        if indicators.get("sharpe", 0) > 1:
            recs.append("Relação risco/retorno atrativa (Sharpe > 1)")
        if not recs:
            recs.append("Sem sinais fortes; avaliar fundamentos e tendência.")
        for rec in recs:
            text.insert(tk.END, f"- {rec}\n")
        text.configure(state="disabled")

    def _boll_position(self, indicators):
        lower = indicators.get("boll_lower")
        upper = indicators.get("boll_upper")
        mid = indicators.get("boll_mid")
        perf = indicators.get("performance", [])
        last_normalized = perf[-1][1] if perf else 0
        if lower is None or upper is None or mid is None:
            return "--"
        if last_normalized < -0.02:
            return "Abaixo da banda inferior (pressão de venda)"
        if last_normalized > 0.02:
            return "Acima da banda superior (possível sobrecompra)"
        if last_normalized > 0:
            return "Entre média e banda superior"
        return "Entre média e banda inferior"

    def _trend_text(self, sma20, sma50, sma200):
        if sma20 and sma50 and sma200:
            if sma20 > sma50 > sma200:
                return "Tendência forte de alta"
            if sma20 < sma50 < sma200:
                return "Tendência forte de baixa"
            return "Tendência neutra ou transição"
        if sma20 and sma50:
            return "Alta" if sma20 > sma50 else "Baixa"
        return "Indefinida"

    def _fill_forecast_tab(self, ticker, forecast):
        text = self.forecast_text
        text.configure(state="normal")
        text.delete("1.0", tk.END)
        if not forecast:
            text.insert(tk.END, "Previsão indisponível (dados insuficientes ou scikit-learn ausente).")
            text.configure(state="disabled")
            return
        metrics = forecast.get("metrics", {})
        text.insert(tk.END, f"Modelo Random Forest - horizonte 30 dias para {ticker}\n")
        text.insert(tk.END, f"MAE: {metrics.get('mae','--')} | RMSE: {metrics.get('rmse','--')} | R²: {metrics.get('r2','--')}\n")
        if forecast.get("feature_importance") is not None:
            fi = ", ".join(f"lag{i+1}:{imp:.3f}" for i, imp in enumerate(forecast["feature_importance"]))
            text.insert(tk.END, f"Importância de features: {fi}\n\n")
        text.insert(tk.END, "Real vs Previsto (primeiros 10):\n")
        for row in forecast.get("forecast", [])[:10]:
            text.insert(
                tk.END,
                f"{row['date']}: previsto R$ {row['predicted']:.2f} | real: "
                f"{row['actual']:.2f if row['actual'] else '--'}\n",
            )
        text.configure(state="disabled")

    def start_compare(self):
        if self.loading:
            return
        raw = self.compare_var.get().upper()
        tickers = [t.strip() for t in raw.split(",") if t.strip()]
        if not tickers:
            messagebox.showwarning("Tickers inválidos", "Informe pelo menos um ticker para comparar")
            return
        if len(tickers) > 10:
            messagebox.showwarning("Limite excedido", "Use no máximo 10 tickers")
            return
        period = self.period_var.get()
        self._set_loading(True, "Comparando tickers...")
        threading.Thread(target=self._load_comparison, args=(tickers, period), daemon=True).start()

    def _load_comparison(self, tickers, period):
        try:
            series_map = {t: fetch_ticker_series(t, period) for t in tickers}
            corr = correlation_matrix(series_map)
            perf_map = {t: normalized_performance(s) for t, s in series_map.items()}
            stats = {}
            for t, series in series_map.items():
                closes = [p["close"] for p in series]
                returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
                stats[t] = {
                    "return": (closes[-1] / closes[0] - 1) if closes else 0,
                    "vol": annualized_volatility(returns),
                    "sharpe": sharpe_ratio(returns),
                }
            self.latest_series = series_map
            self.latest_indicators = stats
            self.master.after(0, self._render_comparison, tickers, corr, perf_map, stats)
        except Exception as exc:  # noqa: BLE001
            self.master.after(0, self._show_error, f"Erro ao comparar: {exc}")

    def _render_comparison(self, tickers, corr, perf_map, stats):
        self._set_loading(False, "Comparação concluída.")
        text = self.compare_text
        text.configure(state="normal")
        text.delete("1.0", tk.END)
        text.insert(tk.END, "Desempenho normalizado (último dia):\n")
        for t in tickers:
            perf = perf_map[t][-1][1] * 100 if perf_map.get(t) else 0
            text.insert(tk.END, f"{t}: {perf:+.2f}%\n")
        text.insert(tk.END, "\nRisco vs Retorno:\n")
        for t, stat in stats.items():
            text.insert(
                tk.END,
                f"{t}: retorno {stat['return']*100:+.2f}% | vol {stat['vol']*100:.2f}% | sharpe {stat['sharpe']:.2f}\n",
            )
        text.insert(tk.END, "\nMatriz de correlação:\n")
        header = "      " + " ".join(f"{t:>7}" for t in tickers)
        text.insert(tk.END, header + "\n")
        for t1 in tickers:
            row = f"{t1:>6} " + " ".join(f"{corr[t1].get(t2,0):>7.2f}" for t2 in tickers)
            text.insert(tk.END, row + "\n")
        text.configure(state="disabled")
        self.notebook.select(self.compare_tab)

    def export_csv(self):
        if not self.latest_series:
            messagebox.showwarning("Nada para exportar", "Execute uma análise primeiro")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="analise_tickers.csv",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "ticker",
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ])
                for ticker, series in self.latest_series.items():
                    for row in series:
                        writer.writerow(
                            [
                                ticker,
                                row.get("date"),
                                row.get("open"),
                                row.get("high"),
                                row.get("low"),
                                row.get("close"),
                                row.get("volume"),
                            ]
                        )
            messagebox.showinfo("Exportação", f"Dados exportados para {file_path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Erro ao exportar", str(exc))


def main():
    root = tk.Tk()
    root.geometry("950x680")
    app = TickerAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
