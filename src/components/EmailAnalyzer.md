# Explicação do EmailAnalyzer

O componente `EmailAnalyzer.jsx` é uma vitrine de como integrar leitura de e-mails, triagem por prioridade e automação de tarefas em um único painel React. Ele funciona com dados simulados para que a interface possa ser demonstrada sem depender de APIs externas.

## Visão geral do fluxo
1. **Sincronização simulada** – ao clicar em “Sincronizar”, a função `analyzeEmails` exibe um estado de carregamento e, após 1,5s, carrega uma lista mock de e-mails.
2. **Classificação por prioridade** – os e-mails são ordenados por urgência (`urgent`, `high`, `medium`, `low`), exibindo cores e ícones diferentes para cada nível.
3. **Painel de integrações** – abas explicam como configurar Outlook 365, ClickUp e um banco de dados, além de listar as dependências de um backend de exemplo.
4. **Leitura detalhada** – ao selecionar um e-mail, o painel lateral mostra remetente, assunto, resumo gerado por IA, anexos e sugestões de tarefa.
5. **Ações rápidas** – botões permitem simular a criação de tarefa no ClickUp e o salvamento do e-mail no banco de dados por meio de `alert`s explicativos.

## Estrutura principal
- **Estado local**: controla lista de e-mails (`emails`), carregamento (`analyzing`), item selecionado (`selectedEmail`), painel de configuração (`showConfig`) e status de integrações (`configured`).
- **Funções utilitárias**: `getPriorityColor`, `getPriorityIcon`, `getPriorityLabel` e `getFileIcon` definem estilos e ícones conforme a prioridade ou tipo de arquivo.
- **Dados de exemplo**: quatro e-mails com assunto, remetente, prioridade, anexos, resumo de IA e tarefa sugerida para ilustrar cenários de incidentes críticos, propostas comerciais e comunicados internos.
- **Renderização**: o layout usa classes utilitárias (Tailwind) para montar cabeçalho, cartões de e-mail, painel detalhado e o hub de configurações por abas.

## Como usar este componente
Inclua `EmailAnalyzer` em uma aplicação React com `lucide-react` instalado. Todo o conteúdo é mockado, então não há chamadas reais a APIs. Para conectar a serviços de e-mail, ClickUp ou banco de dados, substitua o mock em `analyzeEmails` por requisições reais e implemente as ações de backend indicadas no código comentado.
