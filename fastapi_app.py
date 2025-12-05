import csv
import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, conlist

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
            with urlopen(request) as response:  # nosec: B310
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
    url = f"https://stooq.pl/q/d/l/?s={ticker.lower()}.sa&i=d"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request) as response:  # nosec: B310
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
    return {
        "forecast": forecasted,
        "metrics": metrics,
        "feature_importance": getattr(model, "feature_importances_", []),
    }


def forecast_trendline(series, horizon=30):
    if len(series) < 10:
        return None
    closes = [p["close"] for p in series]
    n = len(closes)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(closes) / n
    cov = sum((xs[i] - mean_x) * (closes[i] - mean_y) for i in range(n))
    var = sum((x - mean_x) ** 2 for x in xs)
    slope = cov / var if var else 0
    intercept = mean_y - slope * mean_x

    preds = []
    for idx in range(n, n + horizon):
        preds.append(intercept + slope * idx)

    actual = closes[-horizon:] if len(closes) >= horizon else closes
    metrics = {"mae": None, "rmse": None, "r2": None}
    if actual:
        clipped = preds[: len(actual)]
        errors = [abs(a - p) for a, p in zip(actual, clipped)]
        mae_val = sum(errors) / len(errors)
        rmse_val = math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, clipped)) / len(actual))
        mean_actual = sum(actual) / len(actual)
        ss_tot = sum((a - mean_actual) ** 2 for a in actual)
        ss_res = sum((a - p) ** 2 for a, p in zip(actual, clipped))
        r2_val = 1 - ss_res / ss_tot if ss_tot else 0
        metrics = {"mae": mae_val, "rmse": rmse_val, "r2": r2_val}

    base_date = datetime.strptime(series[-1]["date"], "%Y-%m-%d")
    forecasted = [
        {
            "date": (base_date + timedelta(days=idx + 1)).strftime("%Y-%m-%d"),
            "predicted": preds[idx],
            "actual": actual[idx] if idx < len(actual) else None,
        }
        for idx in range(len(preds))
    ]
    return {"forecast": forecasted, "metrics": metrics, "feature_importance": []}


def build_indicators(series):
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
    return {
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


class ForecastPayload(BaseModel):
    model: str
    metrics: Dict[str, Optional[float]]
    forecast: List[Dict[str, Optional[float]]]
    feature_importance: List[float] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    ticker: str
    period: str
    fundamentals: Dict[str, Optional[str]]
    indicators: Dict[str, Optional[float]]
    forecasts: List[ForecastPayload]
    series: List[Dict[str, float]]


class CompareRequest(BaseModel):
    tickers: conlist(str, min_items=1, max_items=10)
    period: str = Field(default="6m")


class CompareResponse(BaseModel):
    performance: Dict[str, List[List[float]]]
    correlation: Dict[str, Dict[str, float]]
    stats: Dict[str, Dict[str, float]]


app = FastAPI(title="B3 Ticker Analyzer API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def root_page():
    return MOBILE_HTML


@app.get("/api/analyze", response_model=AnalyzeResponse)
async def analyze(ticker: str = Query(..., example="PETR4"), period: str = Query("6m")):
    async def _work():
        series = fetch_ticker_series(ticker.upper(), period)
        fundamentals = fetch_fundamentals(ticker.upper())
        indicators = build_indicators(series)
        rf = forecast_random_forest(series)
        trend = forecast_trendline(series)
        forecasts = []
        if rf:
            forecasts.append(
                ForecastPayload(
                    model="random_forest",
                    metrics=rf["metrics"],
                    forecast=rf["forecast"],
                    feature_importance=list(rf.get("feature_importance", [])),
                )
            )
        if trend:
            forecasts.append(
                ForecastPayload(
                    model="trendline",
                    metrics=trend["metrics"],
                    forecast=trend["forecast"],
                    feature_importance=list(trend.get("feature_importance", [])),
                )
            )
        return AnalyzeResponse(
            ticker=ticker.upper(),
            period=period,
            fundamentals=fundamentals,
            indicators=indicators,
            forecasts=forecasts,
            series=series,
        )

    try:
        return await run_in_threadpool(_work)
    except TickerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/compare", response_model=CompareResponse)
async def compare(request: CompareRequest):
    tickers = [t.upper() for t in request.tickers]

    def _work():
        series_map = {t: fetch_ticker_series(t, request.period) for t in tickers}
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
        performance = {t: [[d, v] for d, v in perf] for t, perf in perf_map.items()}
        return CompareResponse(performance=performance, correlation=corr, stats=stats)

    try:
        return await run_in_threadpool(_work)
    except TickerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


MOBILE_HTML = """
<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>B3 Analyzer - FastAPI</title>
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />
  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin />
  <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap\" rel=\"stylesheet\" />
  <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
  <style>
    :root { color-scheme: dark; }
    body { margin:0; font-family:'Inter',sans-serif; background:#0b1220; color:#e2e8f0; }
    header { padding:18px 16px; background:linear-gradient(120deg,#0ea5e9,#7c3aed); color:#0b1220; }
    h1 { margin:0; font-size:20px; }
    .container { padding:12px; display:flex; flex-direction:column; gap:12px; }
    .card { background:#0f172a; border:1px solid #1f2937; border-radius:12px; padding:12px; box-shadow:0 10px 30px rgba(0,0,0,0.25); }
    .grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); }
    label { display:block; font-weight:600; margin-bottom:6px; }
    input, select, button, textarea { width:100%; padding:10px; border-radius:10px; border:1px solid #1f2937; background:#0b1220; color:#e2e8f0; }
    button { background:#2563eb; color:#fff; font-weight:600; cursor:pointer; border:none; }
    button:disabled { opacity:0.6; cursor:not-allowed; }
    .chips { display:flex; flex-wrap:wrap; gap:6px; }
    .chip { padding:8px 10px; background:#1e293b; border-radius:10px; cursor:pointer; border:1px solid #1f2937; }
    .metrics { display:grid; gap:8px; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); }
    .metric { background:#0b1220; padding:10px; border-radius:10px; border:1px solid #1f2937; }
    pre { white-space:pre-wrap; word-break:break-word; }
    .section-title { display:flex; justify-content:space-between; align-items:center; }
    canvas { max-width:100%; height:280px; }
    @media (min-width:900px) {
      .container { padding:18px; }
      header { padding:22px 18px; }
      h1 { font-size:24px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>B3 Analyzer - FastAPI</h1>
    <div>Pronto para celular e iPad • Responsivo</div>
  </header>
  <div class=\"container\">
    <div class=\"grid\">
      <div class=\"card\">
        <div class=\"section-title\"><h2>Análise</h2><small>Fundamental + Técnico + ML</small></div>
        <label for=\"ticker\">Ticker principal</label>
        <input id=\"ticker\" value=\"PETR4\" />
        <label for=\"period\">Período</label>
        <select id=\"period\">
          <option value=\"1m\">1m</option><option value=\"3m\">3m</option><option value=\"6m\" selected>6m</option><option value=\"1y\">1y</option><option value=\"2y\">2y</option><option value=\"5y\">5y</option>
        </select>
        <button id=\"analyzeBtn\">Analisar</button>
        <div class=\"chips\" id=\"popular\"></div>
        <pre id=\"analysis\">Pronto.</pre>
      </div>
      <div class=\"card\">
        <div class=\"section-title\"><h2>Comparar</h2><small>até 10 tickers</small></div>
        <label for=\"compare\">Tickers (separados por vírgula)</label>
        <input id=\"compare\" value=\"PETR4,VALE3,ITUB4\" />
        <button id=\"compareBtn\">Comparar</button>
        <canvas id=\"chart\"></canvas>
        <pre id=\"compareOut\">Aguardando comparação.</pre>
      </div>
    </div>
  </div>
  <script>
    const popular = document.getElementById('popular');
    const chartCtx = document.getElementById('chart').getContext('2d');
    let chart;

    const sectorMap = %s;
    for (const [sector, list] of Object.entries(sectorMap)) {
      const span = document.createElement('div');
      span.textContent = sector + ':';
      span.style.fontWeight = '600';
      span.style.marginRight = '4px';
      popular.appendChild(span);
      list.forEach(t => {
        const c = document.createElement('span');
        c.textContent = t;
        c.className = 'chip';
        c.onclick = () => { document.getElementById('ticker').value = t; fetchAnalysis(); };
        popular.appendChild(c);
      });
    }

    document.getElementById('analyzeBtn').onclick = fetchAnalysis;
    document.getElementById('compareBtn').onclick = fetchCompare;

    async function fetchAnalysis() {
      const ticker = document.getElementById('ticker').value.trim();
      const period = document.getElementById('period').value;
      if (!ticker) return;
      const out = document.getElementById('analysis');
      out.textContent = 'Carregando...';
      try {
        const res = await fetch(`/api/analyze?ticker=${encodeURIComponent(ticker)}&period=${period}`);
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        const { fundamentals, indicators, forecasts } = data;
        out.textContent = [
          `Ticker: ${data.ticker}.SA (${data.period})`,
          `Setor: ${fundamentals.sector || '--'} | Indústria: ${fundamentals.industry || '--'}`,
          `P/L: ${fundamentals.pe || '--'} | EPS: ${fundamentals.eps || '--'} | Beta: ${fundamentals.beta || '--'}`,
          `SMA 20/50/200: ${fmt(indicators.sma20)} / ${fmt(indicators.sma50)} / ${fmt(indicators.sma200)}`,
          `RSI: ${fmt(indicators.rsi)} | Vol anual: ${(indicators.volatility*100||0).toFixed(2)}% | Sharpe: ${fmt(indicators.sharpe)}`,
          '',
          ...forecasts.map(f => `Modelo ${f.model}: MAE=${fmt(f.metrics.mae)} RMSE=${fmt(f.metrics.rmse)} R2=${fmt(f.metrics.r2)}`),
          '',
          'Últimos 5 candles:',
          ...data.series.slice(-5).map(s => `${s.date}: R$ ${s.close.toFixed(2)} Vol ${s.volume}`),
        ].join('\n');
      } catch (err) {
        out.textContent = 'Erro: ' + err;
      }
    }

    async function fetchCompare() {
      const raw = document.getElementById('compare').value.trim();
      if (!raw) return;
      const tickers = raw.split(',').map(t => t.trim()).filter(Boolean);
      const period = document.getElementById('period').value;
      const out = document.getElementById('compareOut');
      out.textContent = 'Carregando...';
      try {
        const res = await fetch('/api/compare', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ tickers, period })
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        const perf = data.performance;
        renderChart(perf);
        const lines = ['Risco x Retorno'];
        for (const [t, st] of Object.entries(data.stats)) {
          lines.push(`${t}: retorno ${(st.return*100).toFixed(2)}% | vol ${(st.vol*100).toFixed(2)}% | sharpe ${(st.sharpe||0).toFixed(2)}`);
        }
        lines.push('', 'Correlação:');
        for (const [t, row] of Object.entries(data.correlation)) {
          lines.push(`${t}: ${Object.entries(row).map(([k,v]) => `${k}:${v.toFixed(2)}`).join(' ')}`);
        }
        out.textContent = lines.join('\n');
      } catch (err) {
        out.textContent = 'Erro: ' + err;
      }
    }

    function renderChart(perf) {
      const labels = Object.values(perf)[0]?.map(p => p[0]) || [];
      const datasets = Object.entries(perf).map(([ticker, points]) => ({
        label: ticker,
        data: points.map(p => ({ x: p[0], y: (p[1]*100).toFixed(2) })),
        fill:false,
        borderColor: randomColor(),
        tension:0.15
      }));
      if (chart) chart.destroy();
      chart = new Chart(chartCtx, {
        type:'line',
        data:{ labels, datasets },
        options:{
          responsive:true,
          interaction:{ mode:'nearest', intersect:false },
          scales:{ x:{ display:false }, y:{ ticks:{ callback:v=>v+'%' } } },
          plugins:{ legend:{ display:true, position:'bottom' } }
        }
      });
    }

    function randomColor(){
      const hue=Math.floor(Math.random()*360);
      return `hsl(${hue},70%,60%)`;
    }
    function fmt(v){ return v===null||v===undefined?'--':Number(v).toFixed(2); }

    fetchAnalysis();
    fetchCompare();
  </script>
</body>
</html>
""" % json.dumps(POPULAR_BY_SECTOR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
