"""Ferramenta interativa para análise de ações da B3.

Este script baixa dados do Yahoo Finance, calcula indicadores
(tendência, momentum, volatilidade), gera recomendações básicas
com base nesses dados e oferece visualizações rápidas.
"""
from datetime import datetime
from typing import Dict, List, Optional
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import yfinance as yf

warnings.filterwarnings("ignore")

plt.style.use("seaborn-v0_8-darkgrid")
sns.set_palette("husl")
pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", "{:.2f}".format)


class B3StockAnalyzer:
    """Analisador completo de ações da B3."""

    def __init__(self, symbol: str, period: str = "6mo", interval: str = "1d") -> None:
        self.symbol = symbol.upper()
        self.period = period
        self.interval = interval
        self.data: Optional[pd.DataFrame] = None
        self.info: Optional[dict] = None
        self.indicators: Dict[str, pd.Series] = {}
        self.analysis: Dict[str, float] = {}
        self.recommendations: List[Dict[str, str]] = []

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """Baixa dados históricos do Yahoo Finance."""
        try:
            ticker = yf.Ticker(self.symbol)
            self.data = ticker.history(period=self.period, interval=self.interval)
            if self.data.empty:
                raise ValueError(f"Nenhum dado encontrado para {self.symbol}")
            self.info = ticker.info
            return self.data
        except Exception as exc:  # pragma: no cover - dependência externa
            print(f"Erro ao baixar dados: {exc}")
            return None

    def calculate_sma(self, period: int) -> pd.Series:
        return self.data["Close"].rolling(window=period).mean()

    def calculate_ema(self, period: int) -> pd.Series:
        return self.data["Close"].ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, period: int = 14) -> pd.Series:
        delta = self.data["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = self.calculate_ema(fast)
        ema_slow = self.calculate_ema(slow)
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calculate_bollinger_bands(self, period: int = 20, num_std: int = 2) -> tuple[pd.Series, pd.Series, pd.Series]:
        sma = self.calculate_sma(period)
        std = self.data["Close"].rolling(window=period).std()
        upper_band = sma + (std * num_std)
        lower_band = sma - (std * num_std)
        return upper_band, sma, lower_band

    def calculate_volatility(self) -> float:
        returns = self.data["Close"].pct_change()
        volatility = returns.std() * np.sqrt(252) * 100
        return float(volatility)

    def calculate_all_indicators(self) -> Dict[str, pd.Series]:
        self.indicators["SMA_20"] = self.calculate_sma(20)
        self.indicators["SMA_50"] = self.calculate_sma(50)
        self.indicators["SMA_200"] = self.calculate_sma(200)
        self.indicators["EMA_12"] = self.calculate_ema(12)
        self.indicators["EMA_26"] = self.calculate_ema(26)
        self.indicators["RSI"] = self.calculate_rsi(14)
        macd, signal, hist = self.calculate_macd()
        self.indicators["MACD"] = macd
        self.indicators["MACD_Signal"] = signal
        self.indicators["MACD_Hist"] = hist
        upper, middle, lower = self.calculate_bollinger_bands()
        self.indicators["BB_Upper"] = upper
        self.indicators["BB_Middle"] = middle
        self.indicators["BB_Lower"] = lower
        self.indicators["Volatility"] = pd.Series([self.calculate_volatility()] * len(self.data), index=self.data.index)
        return self.indicators

    def analyze_trend(self) -> None:
        current_price = self.data["Close"].iloc[-1]
        sma_20 = self.indicators["SMA_20"].iloc[-1]
        sma_50 = self.indicators["SMA_50"].iloc[-1]
        sma_200 = self.indicators["SMA_200"].iloc[-1]

        if current_price > sma_20 > sma_50:
            trend, trend_emoji = "ALTA (Bullish)", "📈"
        elif current_price < sma_20 < sma_50:
            trend, trend_emoji = "BAIXA (Bearish)", "📉"
        else:
            trend, trend_emoji = "LATERAL (Neutral)", "↔️"

        trend_strength = abs(sma_20 - sma_50) / sma_50 * 100
        self.analysis.update(
            {
                "trend": trend,
                "trend_emoji": trend_emoji,
                "trend_strength": trend_strength,
                "current_price": current_price,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200,
            }
        )

    def analyze_momentum(self) -> None:
        rsi = self.indicators["RSI"].iloc[-1]
        if rsi > 70:
            momentum, momentum_emoji = "SOBRECOMPRADO", "🔴"
        elif rsi < 30:
            momentum, momentum_emoji = "SOBREVENDIDO", "🟢"
        else:
            momentum, momentum_emoji = "NEUTRO", "🟡"

        self.analysis.update({"rsi": rsi, "momentum": momentum, "momentum_emoji": momentum_emoji})

    def analyze_volatility(self) -> None:
        volatility = float(self.indicators["Volatility"].iloc[-1])
        if volatility > 30:
            vol_level, vol_emoji = "ALTA", "⚠️"
        elif volatility > 15:
            vol_level, vol_emoji = "MODERADA", "🟡"
        else:
            vol_level, vol_emoji = "BAIXA", "✅"

        self.analysis.update(
            {"volatility": volatility, "volatility_level": vol_level, "volatility_emoji": vol_emoji}
        )

    def generate_recommendations(self) -> None:
        self.recommendations = []

        if self.analysis["rsi"] < 30:
            self.recommendations.append(
                {
                    "type": "COMPRA 🟢",
                    "title": "RSI Sobrevendido",
                    "description": f"RSI em {self.analysis['rsi']:.1f} indica possível reversão de alta",
                    "confidence": "ALTA",
                }
            )
        elif self.analysis["rsi"] > 70:
            self.recommendations.append(
                {
                    "type": "VENDA 🔴",
                    "title": "RSI Sobrecomprado",
                    "description": f"RSI em {self.analysis['rsi']:.1f} indica possível correção",
                    "confidence": "ALTA",
                }
            )

        if "ALTA" in self.analysis["trend"]:
            self.recommendations.append(
                {
                    "type": "COMPRA 🟢",
                    "title": "Golden Cross",
                    "description": "Médias móveis indicam tendência de alta",
                    "confidence": "MÉDIA",
                }
            )
        elif "BAIXA" in self.analysis["trend"]:
            self.recommendations.append(
                {
                    "type": "VENDA 🔴",
                    "title": "Death Cross",
                    "description": "Médias móveis indicam tendência de baixa",
                    "confidence": "MÉDIA",
                }
            )

        if self.analysis["volatility_level"] == "BAIXA":
            self.recommendations.append(
                {
                    "type": "MANTER 🟡",
                    "title": "Baixa Volatilidade",
                    "description": "Ambiente calmo, considere manter posições",
                    "confidence": "BAIXA",
                }
            )

        macd_current = self.indicators["MACD"].iloc[-1]
        macd_signal = self.indicators["MACD_Signal"].iloc[-1]
        if macd_current > macd_signal:
            self.recommendations.append(
                {
                    "type": "COMPRA 🟢",
                    "title": "MACD Positivo",
                    "description": "MACD acima da linha de sinal",
                    "confidence": "MÉDIA",
                }
            )

    def run_full_analysis(self) -> Optional[Dict[str, float]]:
        if self.fetch_data() is None:
            return None
        self.calculate_all_indicators()
        self.analyze_trend()
        self.analyze_momentum()
        self.analyze_volatility()
        self.generate_recommendations()
        return self.analysis

    def summary(self) -> str:
        lines = [f"Resumo da análise para {self.symbol}"]
        lines.append(f"Preço atual: R$ {self.analysis['current_price']:.2f}")
        change = self.data["Close"].iloc[-1] - self.data["Close"].iloc[-2]
        change_pct = (change / self.data["Close"].iloc[-2]) * 100
        direction = "+" if change >= 0 else ""
        lines.append(f"Variação: {direction}{change:.2f} ({direction}{change_pct:.2f}%)")
        lines.append(f"SMA 20/50/200: {self.analysis['sma_20']:.2f} | {self.analysis['sma_50']:.2f} | {self.analysis['sma_200']:.2f}")
        lines.append(f"RSI (14): {self.analysis['rsi']:.1f}")
        lines.append(f"MACD: {self.indicators['MACD'].iloc[-1]:.2f}")
        lines.append(
            "Tendência: "
            f"{self.analysis['trend_emoji']} {self.analysis['trend']} | "
            f"Momentum: {self.analysis['momentum_emoji']} {self.analysis['momentum']} | "
            f"Volatilidade: {self.analysis['volatility_emoji']} "
            f"{self.analysis['volatility_level']} ({self.analysis['volatility']:.1f}%)"
        )

        if not self.recommendations:
            lines.append("Nenhuma recomendação gerada.")
        else:
            lines.append("Recomendações:")
            for rec in self.recommendations:
                lines.append(
                    f" - {rec['type']} | {rec['title']} (confiança: {rec['confidence']})" f"\n   {rec['description']}"
                )

        lines.append("⚠️ DISCLAIMER: conteúdo educacional, não é recomendação de investimento.")
        return "\n".join(lines)

    def plot_price_chart(self, figsize: tuple[int, int] = (14, 8)) -> None:
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=figsize, gridspec_kw={"height_ratios": [3, 1, 1]})

        ax1.plot(self.data.index, self.data["Close"], label="Preço", linewidth=2, color="#2E86AB")
        ax1.plot(self.data.index, self.indicators["SMA_20"], label="SMA 20", linewidth=1.5, color="#A23B72", linestyle="--")
        ax1.plot(self.data.index, self.indicators["SMA_50"], label="SMA 50", linewidth=1.5, color="#F18F01", linestyle="--")
        ax1.fill_between(
            self.data.index,
            self.indicators["BB_Upper"],
            self.indicators["BB_Lower"],
            alpha=0.1,
            color="gray",
            label="Bollinger Bands",
        )
        ax1.set_title(f"{self.symbol} - Análise Técnica", fontsize=16, fontweight="bold")
        ax1.set_ylabel("Preço (R$)", fontsize=12)
        ax1.legend(loc="best")
        ax1.grid(True, alpha=0.3)

        ax2.plot(self.data.index, self.indicators["RSI"], color="#6A4C93", linewidth=2)
        ax2.axhline(y=70, color="r", linestyle="--", alpha=0.5, label="Sobrecomprado")
        ax2.axhline(y=30, color="g", linestyle="--", alpha=0.5, label="Sobrevendido")
        ax2.fill_between(self.data.index, 70, 100, alpha=0.1, color="red")
        ax2.fill_between(self.data.index, 0, 30, alpha=0.1, color="green")
        ax2.set_ylabel("RSI", fontsize=12)
        ax2.set_ylim([0, 100])
        ax2.legend(loc="best", fontsize=8)
        ax2.grid(True, alpha=0.3)

        ax3.plot(self.data.index, self.indicators["MACD"], label="MACD", color="#2E86AB", linewidth=1.5)
        ax3.plot(self.data.index, self.indicators["MACD_Signal"], label="Signal", color="#F18F01", linewidth=1.5)
        colors = ["green" if x > 0 else "red" for x in self.indicators["MACD_Hist"]]
        ax3.bar(self.data.index, self.indicators["MACD_Hist"], color=colors, alpha=0.3, label="Histogram")
        ax3.set_ylabel("MACD", fontsize=12)
        ax3.set_xlabel("Data", fontsize=12)
        ax3.legend(loc="best", fontsize=8)
        ax3.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()

    def plot_volume_analysis(self, figsize: tuple[int, int] = (14, 6)) -> None:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, gridspec_kw={"height_ratios": [2, 1]})
        ax1.plot(self.data.index, self.data["Close"], linewidth=2, color="#2E86AB")
        ax1.set_title(f"{self.symbol} - Análise de Volume", fontsize=16, fontweight="bold")
        ax1.set_ylabel("Preço (R$)", fontsize=12)
        ax1.grid(True, alpha=0.3)

        colors = ["green" if self.data["Close"].iloc[i] > self.data["Open"].iloc[i] else "red" for i in range(len(self.data))]
        ax2.bar(self.data.index, self.data["Volume"], color=colors, alpha=0.6)
        ax2.set_ylabel("Volume", fontsize=12)
        ax2.set_xlabel("Data", fontsize=12)
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()

    def plot_correlation_matrix(self) -> None:
        df_corr = pd.DataFrame(
            {
                "Preço": self.data["Close"],
                "SMA_20": self.indicators["SMA_20"],
                "SMA_50": self.indicators["SMA_50"],
                "RSI": self.indicators["RSI"],
                "MACD": self.indicators["MACD"],
                "Volume": self.data["Volume"],
            }
        ).dropna()
        corr_matrix = df_corr.corr()
        plt.figure(figsize=(10, 8))
        sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", center=0, fmt=".2f", square=True, linewidths=1, cbar_kws={"shrink": 0.8})
        plt.title(f"{self.symbol} - Matriz de Correlação de Indicadores", fontsize=14, fontweight="bold")
        plt.tight_layout()
        plt.show()

    def export_to_csv(self, filename: Optional[str] = None) -> str:
        if filename is None:
            filename = f"{self.symbol}_{datetime.now().strftime('%Y%m%d')}.csv"
        export_df = self.data.copy()
        for key, value in self.indicators.items():
            export_df[key] = value
        export_df.to_csv(filename)
        return filename


def analyze_symbol(symbol: str = "PETR4.SA", period: str = "6mo") -> Optional[B3StockAnalyzer]:
    analyzer = B3StockAnalyzer(symbol, period=period)
    if analyzer.run_full_analysis() is None:
        return None
    print(analyzer.summary())
    return analyzer


if __name__ == "__main__":
    print("✅ Bibliotecas importadas com sucesso!")
    print(f"📅 Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    analyze_symbol()
