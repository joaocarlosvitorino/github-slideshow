"""Script tudo-em-um para Google Colab (Day Trade e Swing Trade).

Basta colar este arquivo em uma única célula do Colab. Ele instala as
bibliotecas, baixa dados da B3 ou do dólar (USDBRL=X), monta features
sazonais, cria janelas para modelos e treina rapidamente dois modelos
(RandomForest e Gradient Boosting) para prever fechamentos futuros.

Como usar no Colab
------------------
1) Cole tudo em uma célula e execute.
2) Ajuste a lista ``TICKERS`` e os parâmetros ``PERIOD``/``INTERVAL``.
3) Veja o resumo dos downloads e as previsões para cada horizonte.

Observações práticas
--------------------
- Para intraday, o Yahoo Finance costuma limitar o histórico a ~60 dias.
  Use ``period="60d"`` com ``interval="15m"`` ou ``"5m"`` para Day Trade.
- Para dólar, use ``"USDBRL=X"``. Para ações/ETFs da B3, use tickers como
  ``"PETR4"`` ou ``"VALE3"`` (o sufixo ".SA" é adicionado automaticamente).
- Os modelos são exemplos rápidos; ajuste hiperparâmetros conforme a
  estratégia e valide resultados antes de operar.
"""

# 1) Instalação das dependências (Colab)
import sys, subprocess
for pkg in ["yfinance", "pandas", "numpy", "scikit-learn"]:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", pkg], check=False)

import pandas as pd
import numpy as np
import yfinance as yf
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from sklearn.preprocessing import MinMaxScaler
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

# ------------------------------------------------------------
# 2) Utilidades de download e normalização
# ------------------------------------------------------------
VALID_INTERVALS = {
    "1m", "2m", "5m", "15m", "30m", "60m", "90m",
    "1h", "1d", "5d", "1wk", "1mo", "3mo",
}

POPULAR_B3_TICKERS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3", "WEGE3", "ABEV3",
    "LREN3", "MGLU3", "B3SA3", "PRIO3", "RENT3", "CSNA3",
]


@dataclass
class DownloadResult:
    ticker_display: str
    ticker_yf: str
    data: pd.DataFrame
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.data.empty


def normalize_ticker(ticker: str, market: str = "b3") -> Tuple[str, str]:
    cleaned = ticker.strip().upper()
    if market.lower() == "b3":
        cleaned = cleaned.replace(".SA", "")
        return cleaned, f"{cleaned}.SA"
    return cleaned, cleaned


def _validate_interval(interval: str) -> None:
    if interval not in VALID_INTERVALS:
        raise ValueError(f"Intervalo '{interval}' inválido. Opções: {sorted(VALID_INTERVALS)}")


def download_history(
    ticker: str,
    *,
    market: str = "b3",
    period: str = "6mo",
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = False,
) -> DownloadResult:
    _validate_interval(interval)
    ticker_display, ticker_yf = normalize_ticker(ticker, market)

    try:
        asset = yf.Ticker(ticker_yf)
        df = asset.history(
            period=period,
            interval=interval,
            start=start,
            end=end,
            auto_adjust=auto_adjust,
        )
    except Exception as exc:
        return DownloadResult(ticker_display, ticker_yf, pd.DataFrame(), str(exc))

    if df.empty:
        msg = (
            "Nenhum dado retornado. Para intervalos intradiários, tente um "
            "período menor (ex.: 60d) ou valide se o ticker existe no Yahoo."
        )
        return DownloadResult(ticker_display, ticker_yf, df, msg)

    df = df.dropna().copy()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # features sazonais básicas
    df["dow"] = df.index.dayofweek
    df["month"] = df.index.month
    df["doy"] = df.index.dayofyear
    df["valor"] = df["Close"] * df["Volume"]

    return DownloadResult(ticker_display, ticker_yf, df)


def download_batch(
    tickers: Iterable[str],
    *,
    market: str = "b3",
    period: str = "6mo",
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = False,
) -> Dict[str, DownloadResult]:
    results: Dict[str, DownloadResult] = {}
    for t in tickers:
        res = download_history(
            t,
            market=market if t.upper() != "USDBRL=X" else "fx",
            period=period,
            interval=interval,
            start=start,
            end=end,
            auto_adjust=auto_adjust,
        )
        results[res.ticker_display] = res
    return results


def summarize_downloads(results: Dict[str, DownloadResult]) -> None:
    print("Resumo de downloads:")
    for name, res in results.items():
        if res.ok:
            print(f"  • {name}: {len(res.data)} candles ({res.data.index.min()} -> {res.data.index.max()})")
        else:
            print(f"  • {name}: falhou – {res.error}")
    print()

# ------------------------------------------------------------
# 3) Preparação do dataset
# ------------------------------------------------------------

def prepare_windowed_dataset(
    df: pd.DataFrame,
    *,
    window: int = 60,
    horizon: int = 5,
    feature_cols: Optional[List[str]] = None,
    target_col: str = "Close",
) -> Tuple[np.ndarray, np.ndarray, MinMaxScaler]:
    feature_cols = feature_cols or ["Close", "Volume", "valor", "dow", "month", "doy"]
    missing = [c for c in feature_cols + [target_col] if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas ausentes para dataset: {missing}")

    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(df[feature_cols + [target_col]])
    X_scaled = scaled[:, : len(feature_cols)]
    y_scaled = scaled[:, -1]

    X_seq, y_seq = [], []
    for i in range(len(df) - window - horizon + 1):
        X_seq.append(X_scaled[i : i + window])
        y_seq.append(y_scaled[i + window + horizon - 1])

    return np.array(X_seq), np.array(y_seq), scaler

# ------------------------------------------------------------
# 4) Modelagem rápida (tabular para exemplo)
# ------------------------------------------------------------

def train_tabular_models(X_seq: np.ndarray, y_seq: np.ndarray) -> Dict[str, object]:
    X_flat = X_seq.reshape(X_seq.shape[0], -1)
    models = {
        "RandomForest": RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1),
        "GradientBoosting": GradientBoostingRegressor(random_state=42),
    }
    for name, model in models.items():
        model.fit(X_flat, y_seq)
    return models


def evaluate_models(models: Dict[str, object], X_seq: np.ndarray, y_seq: np.ndarray, scaler: MinMaxScaler) -> pd.DataFrame:
    X_flat = X_seq.reshape(X_seq.shape[0], -1)
    metrics = []
    for name, model in models.items():
        pred = model.predict(X_flat)
        mae = mean_absolute_error(y_seq, pred)
        rmse = mean_squared_error(y_seq, pred, squared=False)
        # converte para preço real aproximado usando o inverso do scaler apenas na coluna alvo
        dummy = np.zeros((len(pred), scaler.n_features_in_))
        dummy[:, -1] = pred
        pred_price = scaler.inverse_transform(dummy)[:, -1]
        real_dummy = np.zeros((len(y_seq), scaler.n_features_in_))
        real_dummy[:, -1] = y_seq
        real_price = scaler.inverse_transform(real_dummy)[:, -1]
        mae_price = mean_absolute_error(real_price, pred_price)
        rmse_price = mean_squared_error(real_price, pred_price, squared=False)
        metrics.append({
            "Modelo": name,
            "MAE_scaled": mae,
            "RMSE_scaled": rmse,
            "MAE_preco": mae_price,
            "RMSE_preco": rmse_price,
        })
    return pd.DataFrame(metrics)


def forecast_future(model, last_window: np.ndarray, scaler: MinMaxScaler, steps: List[int]) -> Dict[int, float]:
    forecasts = {}
    window = last_window.copy()
    for step in range(1, max(steps) + 1):
        pred_scaled = model.predict(window.reshape(1, -1))[0]
        dummy = np.zeros((1, scaler.n_features_in_))
        dummy[:, -1] = pred_scaled
        price = scaler.inverse_transform(dummy)[0, -1]
        if step in steps:
            forecasts[step] = price
        # adiciona previsão na janela para próximo passo
        window = np.roll(window, -1, axis=0)
        window[-1, 0] = pred_scaled  # assume primeira feature = Close escalado
    return forecasts

# ------------------------------------------------------------
# 5) Execução padrão (ajuste aqui no Colab)
# ------------------------------------------------------------
TICKERS = ["PETR4", "VALE3", "USDBRL=X"]
PERIOD = "6mo"      # altere para "60d" ou "1y" conforme necessidade
INTERVAL = "1h"     # use "15m" para Day Trade ou "1d" para Swing Trade
WINDOW = 60
HORIZON = 5          # dias/intervalos à frente

if __name__ == "__main__":
    downloads = download_batch(TICKERS, interval=INTERVAL, period=PERIOD)
    summarize_downloads(downloads)

    for name, res in downloads.items():
        if not res.ok:
            print(f"Ignorando {name}: {res.error}")
            continue

        print(f"\n===== {name} =====")
        try:
            X_seq, y_seq, scaler = prepare_windowed_dataset(res.data, window=WINDOW, horizon=HORIZON)
        except ValueError as exc:
            print(f"Erro ao preparar dataset: {exc}")
            continue

        if len(X_seq) < 20:
            print("Poucos dados para treinar; ajuste período/intervalo.")
            continue

        models = train_tabular_models(X_seq, y_seq)
        metrics = evaluate_models(models, X_seq, y_seq, scaler)
        print("Métricas (quanto menor, melhor):")
        print(metrics)

        last_window = X_seq[-1]
        steps = [1, 3, 5, 10]
        for mname, model in models.items():
            fc = forecast_future(model, last_window, scaler, steps)
            print(f"Previsões para {mname} (passos à frente):")
            for step in steps:
                price = fc.get(step)
                if price is not None:
                    print(f"  +{step}: R$ {price:.2f}")

    print("\nDica: use POPULAR_B3_TICKERS para escolher ações líquidas da B3:")
    print(", ".join(POPULAR_B3_TICKERS))
