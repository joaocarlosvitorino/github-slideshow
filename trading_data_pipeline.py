"""Ferramentas robustas para baixar e preparar dados de ativos da B3
(e também do par cambial USD/BRL) para estratégias de Swing Trade e
Day Trade.

Principais pontos de robustez e flexibilidade
---------------------------------------------
- Normaliza tickers do usuário ("petr4", "PETR4.SA" -> "PETR4.SA").
- Aceita pares cambiais do Yahoo Finance ("USDBRL=X") para operar dólar.
- Permite baixar dados diários ou intradiários (1m–1d), validando as
  restrições de cada intervalo e retornando mensagens de erro claras.
- Lida com múltiplos tickers em lote, reportando individualmente quais
  falharam ou ficaram sem dados.
- Adiciona colunas sazonais úteis (dia da semana, mês, dia do ano) e
  normaliza datas para uso direto em modelos.
- Inclui um preparador simples de janelas temporais para redes
  recorrentes/convolucionais sem depender de TensorFlow no momento do
  download.

Onde buscar dados intradiários
------------------------------
- Este módulo usa `yfinance`, que entrega históricos do Yahoo Finance.
  Para intervalos de minutos/horas, o Yahoo limita normalmente a janela
  máxima de ~60 dias. Para Swing Trade, use `period="6mo"` com
  `interval="1h"` ou `"1d"`; para Day Trade, `interval="15m"` ou
  `"5m"` com `period` menor.
- O par dólar é exposto como `USDBRL=X`. Se quiser índice futuro
  (WDO/DOL), procure corretoras ou provedores pagos (Neologica, Tryd,
  MetaTrader, etc.). Este script mantém a compatibilidade com o Yahoo
  Finance por ser gratuito.

Exemplo rápido (após instalar dependências):
-------------------------------------------
>>> from trading_data_pipeline import download_batch, summarize_downloads
>>> dados = download_batch(["PETR4", "VALE3", "USDBRL=X"], interval="1h", period="3mo")
>>> summarize_downloads(dados)

A função imprime quantos candles vieram para cada ticker e alerta se
algum ficou vazio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import yfinance as yf

# Intervalos liberados pelo Yahoo Finance; intervalos intradiários
# costumam permitir no máximo ~60 dias de histórico.
VALID_INTERVALS = {
    "1m", "2m", "5m", "15m", "30m", "60m", "90m",
    "1h", "1d", "5d", "1wk", "1mo", "3mo",
}

# Lista rápida de tickers líquidos na B3 para o usuário escolher.
POPULAR_B3_TICKERS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3", "WEGE3", "ABEV3",
    "LREN3", "MGLU3", "B3SA3", "RAIL3", "PRIO3", "RENT3", "CSNA3",
]


@dataclass
class DownloadResult:
    """Resultado estruturado de um download."""

    ticker_display: str
    ticker_yf: str
    data: pd.DataFrame
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.data.empty


def normalize_ticker(ticker: str, market: str = "b3") -> Tuple[str, str]:
    """Normaliza o ticker digitado.

    - Para ações/ETFs da B3: adiciona sufixo ".SA" caso não exista.
    - Para pares cambiais ou já normalizados: mantém o símbolo.
    """

    cleaned = ticker.strip().upper()
    if market.lower() == "b3":
        cleaned = cleaned.replace(".SA", "")
        return cleaned, f"{cleaned}.SA"
    return cleaned, cleaned


def _validate_interval(interval: str) -> None:
    if interval not in VALID_INTERVALS:
        raise ValueError(
            f"Intervalo '{interval}' inválido. Opções: {sorted(VALID_INTERVALS)}"
        )


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
    """Baixa candles do Yahoo Finance com validação e tratamento de erros.

    Retorna um :class:`DownloadResult` contendo o DataFrame de OHLCV ou a
    mensagem de erro. As colunas seguem o padrão do `yfinance`.
    """

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
    except Exception as exc:  # rede ou API instável
        return DownloadResult(ticker_display, ticker_yf, pd.DataFrame(), str(exc))

    if df.empty:
        msg = (
            "Nenhum dado retornado. Para intervalos intradiários, tente um "
            "período menor (ex.: 60d) ou valide se o ticker existe no Yahoo."
        )
        return DownloadResult(ticker_display, ticker_yf, df, msg)

    df = df.dropna().copy()
    if not df.index.tz is None:
        df.index = df.index.tz_localize(None)

    df["dow"] = df.index.dayofweek
    df["month"] = df.index.month
    df["doy"] = df.index.dayofyear

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
    """Baixa múltiplos tickers e retorna um dicionário indexado pelo ticker."""

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


def prepare_windowed_dataset(
    df: pd.DataFrame,
    *,
    window: int = 60,
    horizon: int = 5,
    feature_cols: Optional[List[str]] = None,
    target_col: str = "Close",
) -> Tuple[pd.DataFrame, pd.Series]:
    """Cria janelas deslizantes simples (sem depender de TF na coleta).

    Retorna um DataFrame (X) com colunas de features empilhadas por tempo
    e uma Série (y) com o valor alvo no horizonte especificado.
    """

    feature_cols = feature_cols or [
        "Close",
        "Volume",
        "dow",
        "month",
        "doy",
    ]
    missing = [c for c in feature_cols + [target_col] if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas ausentes para dataset: {missing}")

    rows = []
    targets = []
    for i in range(len(df) - window - horizon + 1):
        window_slice = df.iloc[i : i + window]
        flat = window_slice[feature_cols].to_numpy().flatten()
        rows.append(flat)
        targets.append(df[target_col].iloc[i + window + horizon - 1])

    X = pd.DataFrame(rows)
    y = pd.Series(targets, name=f"{target_col}_t+{horizon}")
    return X, y


def summarize_downloads(results: Dict[str, DownloadResult]) -> None:
    """Imprime um resumo amigável de vários downloads."""

    print("Resumo de downloads:")
    for name, res in results.items():
        if res.ok:
            print(f"  • {name}: {len(res.data)} candles ({res.data.index.min()} -> {res.data.index.max()})")
        else:
            print(f"  • {name}: falhou – {res.error}")
    print()


if __name__ == "__main__":
    # Exemplo básico focado em robustez para Swing/Day Trade
    tickers = ["PETR4", "VALE3", "USDBRL=X"]
    downloads = download_batch(tickers, interval="1h", period="3mo")
    summarize_downloads(downloads)

    # Se houver dados de PETR4, monta um dataset de janelas para testar
    petr = downloads.get("PETR4")
    if petr and petr.ok:
        X, y = prepare_windowed_dataset(petr.data, window=60, horizon=5)
        print(f"PETR4 -> dataset pronto com {len(X)} amostras e {X.shape[1]} features.")
        print("Mostrando as 3 primeiras linhas:")
        print(X.head(3))
        print(y.head(3))
    else:
        print("Não foi possível montar dataset para PETR4 (sem dados).")
