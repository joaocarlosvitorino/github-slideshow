import json
import math
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


PERIOD_TO_RANGE = {
    "1m": "1mo",
    "3m": "3mo",
    "6m": "6mo",
    "1y": "1y",
}


class TickerError(Exception):
    """Custom error to describe ticker retrieval problems."""


def to_date(timestamp: int) -> str:
    return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")


def fetch_ticker_series(ticker: str, period: str):
    range_value = PERIOD_TO_RANGE.get(period, "6mo")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.SA"
        f"?range={range_value}&interval=1d&events=history&includeAdjustedClose=true"
    )
    try:
        with urlopen(url) as response:
            body = response.read()
    except (HTTPError, URLError) as exc:
        raise TickerError("Falha ao recuperar dados do ticker") from exc

    payload = json.loads(body.decode("utf-8"))
    result = payload.get("chart", {}).get("result", [])
    if not result:
        error_message = payload.get("chart", {}).get("error", {}).get("description")
        raise TickerError(error_message or "Dados indisponíveis")

    record = result[0]
    timestamps = record.get("timestamp", [])
    quote = (record.get("indicators", {}) or {}).get("quote", [{}])[0]
    closes = quote.get("close", [])
    volumes = quote.get("volume", [])

    series = []
    for idx, timestamp in enumerate(timestamps):
        close = closes[idx] if idx < len(closes) else None
        volume = volumes[idx] if idx < len(volumes) else 0
        if close is None or math.isnan(close) or close <= 0:
            continue
        series.append({"date": to_date(timestamp), "close": float(close), "volume": int(volume)})
    return series


def calculate_sma(series, length):
    values = [point["close"] for point in series]
    sma = []
    for idx in range(len(series)):
        if idx + 1 < length:
            sma.append(None)
            continue
        window = values[idx + 1 - length : idx + 1]
        sma.append(sum(window) / length)
    return sma


def calculate_rsi(series, length=14):
    if len(series) < length + 1:
        return []
    gains = []
    losses = []
    for idx in range(1, len(series)):
        delta = series[idx]["close"] - series[idx - 1]["close"]
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


def standard_deviation(values):
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def build_analytics(series):
    if not series:
        return None
    closes = [p["close"] for p in series]
    first = series[0]
    last = series[-1]
    change = last["close"] - first["close"]
    change_percent = (change / first["close"]) * 100
    sma20 = calculate_sma(series, 20)
    sma50 = calculate_sma(series, 50)
    rsi = calculate_rsi(series, 14)
    volatility = standard_deviation(closes[-20:]) * math.sqrt(252)

    return {
        "current": last["close"],
        "change": change,
        "change_percent": change_percent,
        "sma20": sma20[-1],
        "sma50": sma50[-1],
        "trend": "ALTA" if sma20[-1] and sma50[-1] and sma20[-1] > sma50[-1] else "BAIXA",
        "momentum": (
            "SOBRECOMPRADO"
            if rsi and rsi[-1] and rsi[-1] > 70
            else "SOBREVENDIDO" if rsi and rsi[-1] and rsi[-1] < 30 else "NEUTRO"
        ),
        "rsi": rsi[-1] if rsi else None,
        "volatility": volatility,
    }


class TickerAnalyzerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Ticker Analyzer B3 (Tkinter)")
        self.ticker_var = tk.StringVar(value="PETR4")
        self.period_var = tk.StringVar(value="6m")
        self.status_var = tk.StringVar(value="Pronto para analisar.")
        self.loading = False

        self._build_ui()

    def _build_ui(self):
        container = ttk.Frame(self.master, padding=16)
        container.grid(column=0, row=0, sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        ttk.Label(container, text="Ticker B3:").grid(column=0, row=0, sticky="w")
        entry = ttk.Entry(container, textvariable=self.ticker_var, width=12)
        entry.grid(column=1, row=0, sticky="w", padx=(4, 12))
        entry.bind("<Return>", lambda _event: self.start_analyze())

        ttk.Label(container, text="Período:").grid(column=2, row=0, sticky="w")
        period_menu = ttk.OptionMenu(container, self.period_var, self.period_var.get(), *PERIOD_TO_RANGE.keys())
        period_menu.grid(column=3, row=0, sticky="w", padx=(4, 12))

        self.analyze_button = ttk.Button(container, text="Analisar", command=self.start_analyze)
        self.analyze_button.grid(column=4, row=0, sticky="w")

        self.status_label = ttk.Label(container, textvariable=self.status_var, foreground="#334155")
        self.status_label.grid(column=0, row=1, columnspan=5, sticky="w", pady=(8, 4))

        self.result_text = tk.Text(container, height=12, width=70, state="disabled", background="#f8fafc")
        self.result_text.grid(column=0, row=2, columnspan=5, sticky="nsew", pady=(8, 0))

        container.rowconfigure(2, weight=1)

    def start_analyze(self):
        if self.loading:
            return
        ticker = self.ticker_var.get().strip().upper()
        period = self.period_var.get()
        if not ticker:
            messagebox.showwarning("Ticker inválido", "Informe um ticker, como PETR4")
            return

        self._set_loading(True)
        self.status_var.set("Carregando dados...")
        threading.Thread(target=self._load_ticker, args=(ticker, period), daemon=True).start()

    def _set_loading(self, value: bool):
        self.loading = value
        state = tk.DISABLED if value else tk.NORMAL
        self.analyze_button.configure(state=state)

    def _load_ticker(self, ticker: str, period: str):
        try:
            series = fetch_ticker_series(ticker, period)
            analytics = build_analytics(series)
        except TickerError as err:
            self.master.after(0, self._show_error, str(err))
            return
        except Exception as exc:  # noqa: BLE001
            self.master.after(0, self._show_error, f"Erro inesperado: {exc}")
            return

        self.master.after(0, self._render_result, ticker, period, series, analytics)

    def _show_error(self, message: str):
        self._set_loading(False)
        self.status_var.set("Erro ao analisar.")
        messagebox.showerror("Erro", message)

    def _render_result(self, ticker, period, series, analytics):
        self._set_loading(False)
        if not series:
            self.status_var.set("Nenhum dado encontrado.")
            return

        self.status_var.set(f"{ticker}.SA carregado para {period}.")
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)

        self.result_text.insert(tk.END, f"Ticker: {ticker}.SA\n")
        self.result_text.insert(tk.END, f"Período: {period}\n")
        self.result_text.insert(tk.END, f"Último fechamento: R$ {analytics['current']:.2f}\n")
        self.result_text.insert(
            tk.END,
            f"Variação: {analytics['change']:+.2f} ({analytics['change_percent']:+.2f}%)\n",
        )
        self.result_text.insert(tk.END, f"Tendência: {analytics['trend']}\n")
        self.result_text.insert(tk.END, f"RSI: {analytics['rsi']:.2f} ({analytics['momentum']})\n")
        self.result_text.insert(tk.END, f"SMA20: {analytics['sma20']:.2f}\n")
        self.result_text.insert(tk.END, f"SMA50: {analytics['sma50']:.2f}\n")
        self.result_text.insert(tk.END, f"Volatilidade anualizada: {analytics['volatility']:.2f}%\n\n")

        self.result_text.insert(tk.END, "Últimas 10 observações:\n")
        for point in series[-10:]:
            self.result_text.insert(
                tk.END,
                f"{point['date']}: fechamento R$ {point['close']:.2f} | volume {point['volume']}\n",
            )

        self.result_text.configure(state="disabled")


def main():
    root = tk.Tk()
    app = TickerAnalyzerApp(root)
    root.minsize(680, 360)
    root.mainloop()


if __name__ == "__main__":
    main()
