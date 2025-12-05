# Your GitHub Learning Lab Repository for Introducing GitHub

Welcome to **your** repository for your GitHub Learning Lab course. This repository will be used during the different activities that I will be guiding you through. See a word you don't understand? We've included an emoji 📖 next to some key terms. Click on it to see its definition.

Oh! I haven't introduced myself...

I'm the GitHub Learning Lab bot and I'm here to help guide you in your journey to learn and master the various topics covered in this course. I will be using Issue and Pull Request comments to communicate with you. In fact, I already added an issue for you to check out.

![issue tab](https://lab.github.com/public/images/issue_tab.png)

I'll meet you over there, can't wait to get started!

This course is using the :sparkles: open source project [reveal.js](https://github.com/hakimel/reveal.js/). In some cases we’ve made changes to the history so it would behave during class, so head to the original project repo to learn more about the cool people behind this project.

## Guia rápido para baixar dados da B3 e do dólar (Swing/Day Trade)

Use o script `trading_data_pipeline.py` incluído neste repositório para baixar candles diários ou intradiários do Yahoo Finance com validação e mensagens claras:

```bash
python trading_data_pipeline.py
```

- **Escolha de tickers**: o script já traz uma lista de referência (`POPULAR_B3_TICKERS`) e aceita pares como `USDBRL=X` para o dólar à vista. Basta alterar a lista `tickers` no bloco `__main__` ou chamar `download_batch` a partir de outro código.
- **Swing Trade**: utilize `period="6mo"` com `interval="1h"` ou `"1d"` para capturar tendências de médio prazo.
- **Day Trade**: trabalhe com `interval="15m"`, `"5m"` ou `"1m"` e períodos menores (até ~60 dias, limitação do Yahoo Finance). O módulo adiciona colunas sazonais e prepara janelas para modelos de previsão.
- **Dólar**: use `USDBRL=X` para histórico gratuito; para contratos futuros (WDO/DOL), procure feeds profissionais (corretoras/terminals) porque o Yahoo não oferece esses códigos.

A saída informa quantos candles foram baixados, eventuais erros (ex.: ticker inexistente ou período maior que o permitido) e gera um dataset pronto para ser passado a modelos de machine learning.
