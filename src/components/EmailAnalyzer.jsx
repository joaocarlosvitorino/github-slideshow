import React, { useState } from 'react';
import {
  Mail,
  Paperclip,
  AlertCircle,
  Clock,
  CheckCircle,
  FileText,
  Image,
  File,
  Loader2,
  Settings,
  RefreshCw,
  Database,
  ListChecks,
  Zap
} from 'lucide-react';

const EmailAnalyzer = () => {
  const [emails, setEmails] = useState([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [showConfig, setShowConfig] = useState(false);
  const [activeTab, setActiveTab] = useState('outlook');
  const [configured, setConfigured] = useState({
    outlook: false,
    clickup: false,
    database: false
  });

  const analyzeEmails = async () => {
    setAnalyzing(true);

    const mockEmails = [
      {
        id: 1,
        from: 'cliente@empresa.com',
        subject: 'URGENTE: Problema no servidor de produção',
        date: '2025-11-11 14:30',
        preview: 'Nosso sistema está fora do ar há 2 horas...',
        priority: 'urgent',
        requiresResponse: true,
        attachments: [
          {
            name: 'error_log.txt',
            type: 'text',
            size: '45 KB',
            content:
              'ERROR 500: Database connection timeout\nStack trace: ...\nServer: prod-server-01'
          },
          { name: 'screenshot.png', type: 'image', size: '230 KB' }
        ],
        aiSummary: 'Cliente reporta falha crítica no servidor de produção com sistema fora do ar. Requer ação imediata da equipe técnica.',
        suggestedTask: {
          title: 'Resolver problema servidor produção - Cliente ABC',
          priority: 'urgent',
          assignee: 'Equipe DevOps',
          dueDate: '2025-11-11 18:00'
        }
      },
      {
        id: 2,
        from: 'fornecedor@distribuidora.com',
        subject: 'Proposta comercial - Renovação contrato 2025',
        date: '2025-11-11 10:15',
        preview: 'Segue proposta para renovação do contrato...',
        priority: 'high',
        requiresResponse: true,
        attachments: [
          {
            name: 'proposta_2025.pdf',
            type: 'pdf',
            size: '1.2 MB',
            content:
              'PROPOSTA COMERCIAL\n\nValor: R$ 450.000,00\nVigência: 12 meses\nCondições: Pagamento em 3x\nDesconto: 15% para pagamento à vista'
          },
          { name: 'termos.docx', type: 'document', size: '85 KB' }
        ],
        aiSummary: 'Proposta de renovação contratual com valor de R$ 450k. Prazo para resposta: 15 dias. Desconto de 15% disponível para pagamento à vista.',
        suggestedTask: {
          title: 'Analisar proposta renovação contrato 2025',
          priority: 'high',
          assignee: 'Financeiro',
          dueDate: '2025-11-26'
        }
      },
      {
        id: 3,
        from: 'rh@empresa.com',
        subject: 'Aviso: Treinamento de segurança - 15/11',
        date: '2025-11-11 09:00',
        preview: 'Lembramos que o treinamento obrigatório...',
        priority: 'medium',
        requiresResponse: false,
        attachments: [
          {
            name: 'agenda_treinamento.pdf',
            type: 'pdf',
            size: '156 KB',
            content:
              'AGENDA DE TREINAMENTO\n\nData: 15/11/2025\nHorário: 14h-16h\nLocal: Sala de conferências A\nTópicos: Segurança da informação, LGPD'
          }
        ],
        aiSummary:
          'Comunicado informativo sobre treinamento obrigatório de segurança. Data: 15/11 às 14h. Apenas para conhecimento.',
        suggestedTask: null
      },
      {
        id: 4,
        from: 'diretor@empresa.com',
        subject: 'Reunião estratégica - Feedback necessário até hoje',
        date: '2025-11-11 08:45',
        preview: 'Precisamos alinhar a estratégia para Q1 2026...',
        priority: 'urgent',
        requiresResponse: true,
        attachments: [
          {
            name: 'estrategia_q1.xlsx',
            type: 'spreadsheet',
            size: '420 KB',
            content:
              'PLANEJAMENTO Q1 2026\n\nMetas:\n- Crescimento: 25%\n- Novos clientes: 150\n- Receita: R$ 2.5M\n\nPrazo feedback: 11/11 18h'
          }
        ],
        aiSummary:
          'Diretor solicita feedback urgente sobre planejamento estratégico Q1/2026. Deadline: hoje às 18h. Documentos incluem metas e orçamento.',
        suggestedTask: {
          title: 'Revisar e dar feedback planejamento Q1 2026',
          priority: 'urgent',
          assignee: 'Você',
          dueDate: '2025-11-11 18:00'
        }
      }
    ];

    await new Promise((resolve) => setTimeout(resolve, 1500));
    setEmails(mockEmails);
    setAnalyzing(false);
  };

  const createTaskInClickUp = (email) => {
    if (!email.suggestedTask) return;

    alert(
      `✅ Tarefa criada no ClickUp:\n\n${email.suggestedTask.title}\n\nPrioridade: ${email.suggestedTask.priority}\nResponsável: ${email.suggestedTask.assignee}\nPrazo: ${email.suggestedTask.dueDate}\n\n(Em produção, isso seria enviado via API do ClickUp)`
    );
  };

  const saveToDatabase = (email) => {
    alert(
      `💾 E-mail salvo no banco de dados:\n\nID: ${email.id}\nAssunto: ${email.subject}\nPrioridade: ${email.priority}\nAnexos: ${email.attachments.length}\n\n(Em produção, isso seria salvo no seu banco de dados)`
    );
  };

  const getPriorityColor = (priority) => {
    const colors = {
      urgent: 'bg-red-100 text-red-800 border-red-300',
      high: 'bg-orange-100 text-orange-800 border-orange-300',
      medium: 'bg-yellow-100 text-yellow-800 border-yellow-300',
      low: 'bg-gray-100 text-gray-800 border-gray-300'
    };
    return colors[priority] || colors.low;
  };

  const getPriorityIcon = (priority) => {
    if (priority === 'urgent') return <AlertCircle className="w-5 h-5" />;
    if (priority === 'high') return <Clock className="w-5 h-5" />;
    return <CheckCircle className="w-5 h-5" />;
  };

  const getPriorityLabel = (priority) => {
    const labels = {
      urgent: 'URGENTE',
      high: 'Alta Prioridade',
      medium: 'Média Prioridade',
      low: 'Baixa Prioridade'
    };
    return labels[priority] || 'Normal';
  };

  const getFileIcon = (type) => {
    if (type === 'image') return <Image className="w-4 h-4" />;
    if (type === 'pdf' || type === 'document') return <FileText className="w-4 h-4" />;
    return <File className="w-4 h-4" />;
  };

  const sortedEmails = [...emails].sort((a, b) => {
    const priorityOrder = { urgent: 0, high: 1, medium: 2, low: 3 };
    return priorityOrder[a.priority] - priorityOrder[b.priority];
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Mail className="w-8 h-8 text-white" />
                <div>
                  <h1 className="text-2xl font-bold text-white">
                    Hub de Gerenciamento Integrado
                  </h1>
                  <p className="text-blue-100 text-sm">
                    E-mails + ClickUp + Banco de Dados
                  </p>
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowConfig(!showConfig)}
                  className="bg-white/20 text-white px-4 py-2 rounded-lg font-semibold hover:bg-white/30 transition-colors flex items-center gap-2"
                >
                  <Settings className="w-5 h-5" />
                  Configurar Integrações
                </button>
                <button
                  onClick={analyzeEmails}
                  disabled={analyzing}
                  className="bg-white text-blue-600 px-6 py-2 rounded-lg font-semibold hover:bg-blue-50 transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                  {analyzing ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Analisando...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-5 h-5" />
                      Sincronizar
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Status das Integrações */}
            <div className="flex gap-3 mt-4">
              <div
                className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm ${
                  configured.outlook
                    ? 'bg-green-400 text-green-900'
                    : 'bg-white/20 text-white'
                }`}
              >
                <Mail className="w-4 h-4" />
                Outlook {configured.outlook ? '✓' : '○'}
              </div>
              <div
                className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm ${
                  configured.clickup
                    ? 'bg-green-400 text-green-900'
                    : 'bg-white/20 text-white'
                }`}
              >
                <ListChecks className="w-4 h-4" />
                ClickUp {configured.clickup ? '✓' : '○'}
              </div>
              <div
                className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm ${
                  configured.database
                    ? 'bg-green-400 text-green-900'
                    : 'bg-white/20 text-white'
                }`}
              >
                <Database className="w-4 h-4" />
                Database {configured.database ? '✓' : '○'}
              </div>
            </div>
          </div>

          {/* Painel de Configuração */}
          {showConfig && (
            <div className="bg-gradient-to-r from-purple-50 to-blue-50 p-6 border-b-2 border-blue-200">
              <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
                <Zap className="w-6 h-6" />
                Central de Integrações
              </h2>

              {/* Tabs */}
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => setActiveTab('outlook')}
                  className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                    activeTab === 'outlook'
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <Mail className="w-4 h-4 inline mr-2" />
                  Outlook 365
                </button>
                <button
                  onClick={() => setActiveTab('clickup')}
                  className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                    activeTab === 'clickup'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <ListChecks className="w-4 h-4 inline mr-2" />
                  ClickUp
                </button>
                <button
                  onClick={() => setActiveTab('database')}
                  className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                    activeTab === 'database'
                      ? 'bg-green-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <Database className="w-4 h-4 inline mr-2" />
                  Banco de Dados
                </button>
                <button
                  onClick={() => setActiveTab('integration')}
                  className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                    activeTab === 'integration'
                      ? 'bg-orange-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <Zap className="w-4 h-4 inline mr-2" />
                  Código Integrado
                </button>
              </div>

              {/* Conteúdo das Tabs */}
              <div className="bg-white rounded-lg p-6">
                {activeTab === 'outlook' && (
                  <div className="space-y-4">
                    <h3 className="font-bold text-lg text-blue-900">
                      📧 Configuração Outlook 365
                    </h3>
                    <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                      <p className="text-sm mb-2">
                        <strong>Credenciais do Azure Portal:</strong>
                      </p>
                      <ul className="text-sm space-y-1 list-disc ml-5">
                        <li>Application (client) ID</li>
                        <li>Directory (tenant) ID</li>
                        <li>Client Secret</li>
                        <li>Permissões: Mail.Read, Mail.ReadWrite, User.Read</li>
                      </ul>
                    </div>
                    <button
                      onClick={() =>
                        setConfigured({ ...configured, outlook: true })
                      }
                      className="bg-blue-600 text-white px-6 py-2 rounded-lg font-semibold hover:bg-blue-700 w-full"
                    >
                      Marcar como Configurado
                    </button>
                  </div>
                )}

                {activeTab === 'clickup' && (
                  <div className="space-y-4">
                    <h3 className="font-bold text-lg text-purple-900">
                      ✅ Configuração ClickUp
                    </h3>
                    <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                      <p className="text-sm mb-2">
                        <strong>Como obter a API Key:</strong>
                      </p>
                      <ol className="text-sm space-y-1 list-decimal ml-5">
                        <li>Acesse ClickUp → Settings → Apps</li>
                        <li>Clique em "Generate" na seção API Token</li>
                        <li>Copie o token gerado</li>
                        <li>API Base: https://api.clickup.com/api/v2/</li>
                      </ol>
                    </div>
                    <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                      <p className="text-sm mb-2">
                        <strong>Recursos disponíveis:</strong>
                      </p>
                      <ul className="text-sm space-y-1 list-disc ml-5">
                        <li>Criar tarefas automaticamente dos e-mails</li>
                        <li>Adicionar anexos às tarefas</li>
                        <li>Atribuir responsáveis com base no remetente</li>
                        <li>Definir prioridades e prazos automaticamente</li>
                      </ul>
                    </div>
                    <button
                      onClick={() =>
                        setConfigured({ ...configured, clickup: true })
                      }
                      className="bg-purple-600 text-white px-6 py-2 rounded-lg font-semibold hover:bg-purple-700 w-full"
                    >
                      Marcar como Configurado
                    </button>
                  </div>
                )}

                {activeTab === 'database' && (
                  <div className="space-y-4">
                    <h3 className="font-bold text-lg text-green-900">
                      💾 Configuração Banco de Dados
                    </h3>
                    <div className="bg-green-50 p-4 rounded-lg border border-green-200">
                      <p className="text-sm mb-2">
                        <strong>Opções de Banco de Dados para seu Servidor:</strong>
                      </p>
                      <ul className="text-sm space-y-2">
                        <li className="font-semibold">
                          PostgreSQL (Recomendado)
                          <p className="text-xs text-gray-700 mt-1">
                            No servidor: npm install pg
                            <br />
                            Connection: postgresql://user:password@localhost:5432/emails_db
                          </p>
                        </li>
                        <li className="font-semibold">
                          MongoDB
                          <p className="text-xs text-gray-700 mt-1">
                            No servidor: npm install mongoose
                            <br />
                            Connection: mongodb://localhost:27017/emails_db
                          </p>
                        </li>
                        <li className="font-semibold">
                          MySQL
                          <p className="text-xs text-gray-700 mt-1">
                            No servidor: npm install mysql2
                            <br />
                            Connection: mysql://user:password@localhost:3306/emails_db
                          </p>
                        </li>
                      </ul>
                      <p className="text-xs text-gray-600 mt-3">
                        💡 Esses comandos são para executar no SEU SERVIDOR backend, não neste app.
                      </p>
                    </div>
                    <div className="bg-green-50 p-4 rounded-lg border border-green-200">
                      <p className="text-sm mb-2">
                        <strong>Dados que serão armazenados:</strong>
                      </p>
                      <ul className="text-sm space-y-1 list-disc ml-5">
                        <li>Informações completas dos e-mails</li>
                        <li>Anexos (metadados e conteúdo)</li>
                        <li>Análises de prioridade e IA</li>
                        <li>Histórico de tarefas criadas</li>
                        <li>Logs de sincronização</li>
                      </ul>
                    </div>
                    <button
                      onClick={() =>
                        setConfigured({ ...configured, database: true })
                      }
                      className="bg-green-600 text-white px-6 py-2 rounded-lg font-semibold hover:bg-green-700 w-full"
                    >
                      Marcar como Configurado
                    </button>
                  </div>
                )}

                {activeTab === 'integration' && (
                  <div className="space-y-4">
                    <h3 className="font-bold text-lg text-orange-900">
                      🔗 Código Backend Integrado Completo
                    </h3>

                    <div className="bg-orange-50 p-4 rounded-lg border border-orange-200">
                      <p className="text-sm mb-2">
                        <strong>📦 Dependências necessárias:</strong>
                      </p>
                      <pre className="text-xs bg-gray-900 text-green-400 p-3 rounded">
                        npm install express @microsoft/microsoft-graph-client @azure/msal-node cors dotenv axios
                      </pre>
                      <p className="text-xs text-orange-700 mt-2">
                        💡 Para banco de dados, adicione: <code>pg</code> (PostgreSQL), <code>mongoose</code> (MongoDB) ou
                        <code>mysql2</code> (MySQL)
                      </p>
                    </div>

                    <div className="max-h-96 overflow-y-auto">
                      <p className="text-sm font-bold mb-2">
                        📄 server-integrado.js (Código Completo):
                      </p>
                      <pre className="text-xs bg-gray-900 text-green-400 p-4 rounded overflow-x-auto">
                        {`// server-integrado.js - Hub de Integração Completo
require('dotenv').config();
const express = require('express');
const cors = require('cors');
const msal = require('@azure/msal-node');
const graph = require('@microsoft/microsoft-graph-client');
const axios = require('axios');
// Para PostgreSQL: npm install pg
// Para MongoDB: npm install mongoose
// Para MySQL: npm install mysql2

const app = express();
app.use(cors());
app.use(express.json());

// ==================== CONFIGURAÇÕES ====================

// Outlook/Microsoft Graph
const msalConfig = {
  auth: {
    clientId: process.env.OUTLOOK_CLIENT_ID,
    authority: \`https://login.microsoftonline.com/\${process.env.OUTLOOK_TENANT_ID}\`,
    clientSecret: process.env.OUTLOOK_CLIENT_SECRET
  }
};
const pca = new msal.ConfidentialClientApplication(msalConfig);
let outlookToken = null;

// ClickUp
const CLICKUP_API_KEY = process.env.CLICKUP_API_KEY;
const CLICKUP_LIST_ID = process.env.CLICKUP_LIST_ID;
const clickupHeaders = {
  'Authorization': CLICKUP_API_KEY,
  'Content-Type': 'application/json'
};

// ==================== CONFIGURAÇÃO DO BANCO ====================
// Escolha um dos bancos abaixo:

// OPÇÃO 1: PostgreSQL
// const { Pool } = require('pg');
// const pool = new Pool({ connectionString: process.env.DATABASE_URL });

// OPÇÃO 2: MongoDB
// const mongoose = require('mongoose');
// mongoose.connect(process.env.MONGODB_URL);

// OPÇÃO 3: MySQL
// const mysql = require('mysql2/promise');
// const pool = mysql.createPool(process.env.MYSQL_URL);

// Para este exemplo, vamos usar um sistema simples em memória
// Em produção, substitua por um dos bancos acima
const emailsDB = new Map();
const attachmentsDB = new Map();
const syncLogsDB = [];

// ==================== FUNÇÕES DO BANCO ====================

async function saveEmailToDatabase(emailData) {
  emailsDB.set(emailData.id, {
    ...emailData,
    created_at: new Date()
  });
  return true;
}

async function getEmailsFromDatabase() {
  return Array.from(emailsDB.values())
    .sort((a, b) => new Date(b.receivedDate) - new Date(a.receivedDate))
    .slice(0, 50);
}

async function saveAttachment(emailId, attachment) {
  const key = \`\${emailId}_\${attachment.filename}\`;
  attachmentsDB.set(key, {
    email_id: emailId,
    ...attachment,
    created_at: new Date()
  });
}

async function getAttachments(emailId) {
  return Array.from(attachmentsDB.values())
    .filter(att => att.email_id === emailId);
}

async function saveSyncLog(log) {
  syncLogsDB.push({
    ...log,
    sync_date: new Date()
  });
}

// ==================== AUTENTICAÇÃO OUTLOOK ====================

app.get('/auth/signin', (req, res) => {
  const authCodeUrlParameters = {
    scopes: ['user.read', 'mail.read', 'mail.readwrite'],
    redirectUri: process.env.REDIRECT_URI
  };

  pca.getAuthCodeUrl(authCodeUrlParameters).then((response) => {
    res.redirect(response);
  });
});

app.get('/callback', async (req, res) => {
  const tokenRequest = {
    code: req.query.code,
    scopes: ['user.read', 'mail.read', 'mail.readwrite'],
    redirectUri: process.env.REDIRECT_URI
  };

  try {
    const response = await pca.acquireTokenByCode(tokenRequest);
    outlookToken = response.accessToken;
    res.send('<h1>✅ Autenticação bem-sucedida!</h1>');
  } catch (error) {
    res.status(500).send('Erro na autenticação');
  }
});

// ==================== FUNÇÕES AUXILIARES ====================

function getGraphClient(token) {
  return graph.Client.init({
    authProvider: (done) => done(null, token)
  });
}

function analyzePriority(subject, isRead, hasAttachments) {
  const subjectLower = subject.toLowerCase();

  if (subjectLower.includes('urgente') || subjectLower.includes('urgent') || 
      subjectLower.includes('asap')) {
    return 'urgent';
  } else if (subjectLower.includes('importante') || subjectLower.includes('prioridade') ||
             !isRead) {
    return 'high';
  } else if (hasAttachments) {
    return 'medium';
  }
  return 'low';
}


async function createClickUpTask(emailData) {
  try {
    const taskData = {
      name: \`Email: \${emailData.subject}\`,
      description: \`**De:** \${emailData.sender}\\n**Data:** \${emailData.date}\\n\\n**Conteúdo:**\\n\${emailData.bodyPreview}\`,
      priority: emailData.priority === 'urgent' ? 1 : emailData.priority === 'high' ? 2 : 3,
      status: 'to do',
      due_date: emailData.dueDate ? new Date(emailData.dueDate).getTime() : null
    };

    const response = await axios.post(
      \`https://api.clickup.com/api/v2/list/\${CLICKUP_LIST_ID}/task\`,
      taskData,
      { headers: clickupHeaders }
    );

    return response.data.id;
  } catch (error) {
    console.error('Erro ao criar tarefa no ClickUp:', error);
    return null;
  }
}

// ==================== ENDPOINTS PRINCIPAIS ====================

// Sincronização completa
app.post('/api/sync', async (req, res) => {
  if (!outlookToken) {
    return res.status(401).json({ error: 'Não autenticado' });
  }

  try {
    const client = getGraphClient(outlookToken);

    // Buscar e-mails do Outlook
    const messages = await client
      .api('/me/messages')
      .top(50)
      .select('id,subject,from,receivedDateTime,bodyPreview,hasAttachments,isRead')
      .orderby('receivedDateTime DESC')
      .get();

    let emailsProcessed = 0;
    let tasksCreated = 0;

    for (const msg of messages.value) {
      const priority = analyzePriority(msg.subject, msg.isRead, msg.hasAttachments);

      const emailData = {
        id: msg.id,
        subject: msg.subject,
        sender: msg.from.emailAddress.address,
        receivedDate: msg.receivedDateTime,
        bodyPreview: msg.bodyPreview,
        priority: priority,
        hasAttachments: msg.hasAttachments,
        isRead: msg.isRead,
        date: new Date(msg.receivedDateTime).toLocaleString('pt-BR')
      };

      // Salvar no banco de dados
      await saveEmailToDatabase(emailData);
      emailsProcessed++;

      // Criar tarefa no ClickUp se for prioritário
      if ((priority === 'urgent' || priority === 'high') && !msg.isRead) {
        const taskId = await createClickUpTask(emailData);
        if (taskId) {
          emailData.clickupTaskId = taskId;
          await saveEmailToDatabase(emailData);
          tasksCreated++;
        }
      }

      // Processar anexos se existirem
      if (msg.hasAttachments) {
        const attachments = await client
          .api(\`/me/messages/\${msg.id}/attachments\`)
          .get();

        for (const att of attachments.value) {
          await saveAttachment(msg.id, {
            filename: att.name,
            content_type: att.contentType,
            size: att.size
          });
        }
      }
    }

    // Registrar log de sincronização
    await saveSyncLog({
      emails_processed: emailsProcessed,
      tasks_created: tasksCreated,
      status: 'success'
    });

    res.json({
      success: true,
      emailsProcessed,
      tasksCreated,
      message: 'Sincronização completa realizada com sucesso'
    });
  } catch (error) {
    console.error('Erro na sincronização:', error);
    res.status(500).json({ error: 'Erro na sincronização' });
  }
});

// Buscar e-mails do banco de dados
app.get('/api/emails', async (req, res) => {
  try {
    const emails = await getEmailsFromDatabase();
    res.json(emails);
  } catch (error) {
    res.status(500).json({ error: 'Erro ao buscar e-mails' });
  }
});

// Buscar anexos de um e-mail
app.get('/api/emails/:id/attachments', async (req, res) => {
  try {
    const attachments = await getAttachments(req.params.id);
    res.json(attachments);
  } catch (error) {
    res.status(500).json({ error: 'Erro ao buscar anexos' });
  }
});

// Estatísticas
app.get('/api/stats', async (req, res) => {
  try {
    const allEmails = await getEmailsFromDatabase();

    const stats = {
      total_emails: allEmails.length,
      urgent_emails: allEmails.filter((e) => e.priority === 'urgent').length,
      tasks_created: allEmails.filter((e) => e.clickupTaskId).length,
      unread_emails: allEmails.filter((e) => !e.isRead).length
    };

    res.json(stats);
  } catch (error) {
    res.status(500).json({ error: 'Erro ao buscar estatísticas' });
  }
});

// Criar tarefa manualmente no ClickUp
app.post('/api/create-task', async (req, res) => {
  try {
    const taskId = await createClickUpTask(req.body);
    res.json({ success: true, taskId });
  } catch (error) {
    res.status(500).json({ error: 'Erro ao criar tarefa' });
  }
});

const PORT = 3000;
app.listen(PORT, () => {
  console.log(\`\\n🚀 Servidor integrado rodando em http://localhost:\${PORT}\`);
  console.log(\`\\n📧 Outlook: http://localhost:\${PORT}/auth/signin\`);
  console.log(\`📊 Estatísticas: http://localhost:\${PORT}/api/stats\`);
  console.log(\`🔄 Sincronizar: POST http://localhost:\${PORT}/api/sync\\n\`);
});`}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3">
            <div className="lg:col-span-1 border-r border-gray-200 bg-gray-50">
              <div className="p-4 border-b border-gray-200 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-800">
                  Caixa de Entrada Priorizada
                </h2>
                <span className="text-sm text-gray-500">
                  {sortedEmails.length} e-mails
                </span>
              </div>

              <div className="divide-y divide-gray-200">
                {sortedEmails.map((email) => (
                  <button
                    key={email.id}
                    onClick={() => setSelectedEmail(email)}
                    className={`w-full text-left p-4 hover:bg-white transition-colors flex flex-col gap-2 ${
                      selectedEmail?.id === email.id ? 'bg-white shadow-inner' : ''
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-gray-800">
                        {email.from}
                      </span>
                      <span className="text-xs text-gray-500">{email.date}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-full border ${getPriorityColor(
                          email.priority
                        )}`}
                      >
                        {getPriorityIcon(email.priority)}
                        {getPriorityLabel(email.priority)}
                      </span>
                      {email.requiresResponse && (
                        <span className="text-xs text-orange-600 bg-orange-100 px-2 py-1 rounded-full">
                          Resposta Necessária
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 font-medium">
                      {email.subject}
                    </p>
                    <p className="text-xs text-gray-500 line-clamp-2">
                      {email.preview}
                    </p>
                    {email.attachments.length > 0 && (
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <Paperclip className="w-3 h-3" />
                        {email.attachments.length} anexos
                      </div>
                    )}
                  </button>
                ))}

                {sortedEmails.length === 0 && !analyzing && (
                  <div className="p-6 text-center text-gray-500 text-sm">
                    Clique em "Sincronizar" para analisar seus e-mails.
                  </div>
                )}
              </div>
            </div>

            <div className="lg:col-span-2">
              {selectedEmail ? (
                <div className="p-6 space-y-6">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs uppercase font-bold text-gray-500">
                          De
                        </span>
                        <span className="text-sm font-semibold text-gray-800">
                          {selectedEmail.from}
                        </span>
                      </div>
                      <h2 className="text-xl font-bold text-gray-900 mt-2">
                        {selectedEmail.subject}
                      </h2>
                      <div className="flex items-center gap-2 mt-2">
                        <span
                          className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-full border ${getPriorityColor(
                            selectedEmail.priority
                          )}`}
                        >
                          {getPriorityIcon(selectedEmail.priority)}
                          {getPriorityLabel(selectedEmail.priority)}
                        </span>
                        <span className="text-xs text-gray-500">
                          Recebido em {selectedEmail.date}
                        </span>
                        {selectedEmail.requiresResponse && (
                          <span className="text-xs text-orange-600 bg-orange-100 px-2 py-1 rounded-full">
                            Requer Resposta
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => createTaskInClickUp(selectedEmail)}
                        className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-semibold hover:bg-purple-700 transition-colors flex items-center gap-2"
                      >
                        <ListChecks className="w-4 h-4" />
                        Criar tarefa
                      </button>
                      <button
                        onClick={() => saveToDatabase(selectedEmail)}
                        className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-semibold hover:bg-green-700 transition-colors flex items-center gap-2"
                      >
                        <Database className="w-4 h-4" />
                        Salvar
                      </button>
                    </div>
                  </div>

                  <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
                    <h3 className="text-sm font-bold text-blue-900 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" />
                      Análise Inteligente do E-mail
                    </h3>
                    <p className="text-sm text-blue-800 mt-2">
                      {selectedEmail.aiSummary}
                    </p>
                  </div>

                  {selectedEmail.suggestedTask ? (
                    <div className="bg-purple-50 border border-purple-100 rounded-xl p-4">
                      <h3 className="text-sm font-bold text-purple-900 flex items-center gap-2">
                        <ListChecks className="w-4 h-4" />
                        Tarefa Sugerida
                      </h3>
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm text-gray-700">
                        <div>
                          <span className="font-semibold block text-gray-900">
                            Título
                          </span>
                          {selectedEmail.suggestedTask.title}
                        </div>
                        <div>
                          <span className="font-semibold block text-gray-900">
                            Prioridade
                          </span>
                          {getPriorityLabel(selectedEmail.suggestedTask.priority)}
                        </div>
                        <div>
                          <span className="font-semibold block text-gray-900">
                            Responsável
                          </span>
                          {selectedEmail.suggestedTask.assignee}
                        </div>
                        <div>
                          <span className="font-semibold block text-gray-900">
                            Prazo
                          </span>
                          {selectedEmail.suggestedTask.dueDate}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-sm text-gray-600">
                      Nenhuma tarefa sugerida para este e-mail.
                    </div>
                  )}

                  <div>
                    <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                      <Paperclip className="w-4 h-4" />
                      Anexos ({selectedEmail.attachments.length})
                    </h3>
                    {selectedEmail.attachments.length > 0 ? (
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                        {selectedEmail.attachments.map((attachment) => (
                          <div
                            key={attachment.name}
                            className="border border-gray-200 rounded-lg p-3 flex items-center gap-3 bg-gray-50"
                          >
                            <div className="p-2 bg-white rounded-full shadow-sm">
                              {getFileIcon(attachment.type)}
                            </div>
                            <div className="flex-1">
                              <p className="text-sm font-semibold text-gray-800">
                                {attachment.name}
                              </p>
                              <p className="text-xs text-gray-500">{attachment.size}</p>
                            </div>
                            {attachment.content && (
                              <button className="text-xs text-blue-600 hover:underline">
                                Ver conteúdo
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 mt-2">
                        Nenhum anexo disponível.
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="p-10 text-center text-gray-500">
                  <div className="mx-auto w-24 h-24 bg-blue-100 rounded-full flex items-center justify-center mb-4">
                    <Mail className="w-12 h-12 text-blue-500" />
                  </div>
                  <h2 className="text-xl font-semibold text-gray-700">
                    Selecione um e-mail para ver detalhes
                  </h2>
                  <p className="text-sm mt-2">
                    Após a análise, você verá aqui o conteúdo completo do e-mail, as
                    recomendações inteligentes e os anexos.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmailAnalyzer;

