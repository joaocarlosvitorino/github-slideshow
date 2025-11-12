# ========================================
# ORQUESTRADOR CENTRAL - HUB DE INTEGRAÇÃO
# Sistema unificado para gerenciar:
# - E-mails (Outlook 365)
# - PDFs de Válvulas
# - ClickUp (Tarefas)
# - PostgreSQL (Banco Central)
# ========================================

"""
INSTALAÇÃO COMPLETA:
pip install msal requests pandas sqlalchemy psycopg2-binary openpyxl python-dotenv
pip install PyPDF2 pdfplumber tabula-py
pip install schedule APScheduler
pip install flask flask-cors
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path
import pandas as pd

# Importações de integração
import msal
import requests
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

# Importações para PDF
import PyPDF2
import pdfplumber
try:
    import tabula
except:
    print("⚠️ Tabula não instalado. Para tabelas em PDF: pip install tabula-py")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('orchestrator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('Orchestrator')

# ========================================
# CONFIGURAÇÕES GLOBAIS
# ========================================


class Config:
    """Configurações centralizadas do sistema"""

    # PostgreSQL
    DATABASE_URL = os.getenv(
        'DATABASE_URL',
        'postgresql://usuario:senha@localhost:5432/hub_industrial'
    )

    # Outlook 365
    OUTLOOK_CLIENT_ID = os.getenv('OUTLOOK_CLIENT_ID', '')
    OUTLOOK_CLIENT_SECRET = os.getenv('OUTLOOK_CLIENT_SECRET', '')
    OUTLOOK_TENANT_ID = os.getenv('OUTLOOK_TENANT_ID', '')
    OUTLOOK_USER_ID = os.getenv('OUTLOOK_USER_ID', '')  # Pode ser e-mail ou ID do usuário

    # ClickUp
    CLICKUP_API_KEY = os.getenv('CLICKUP_API_KEY', '')
    CLICKUP_LIST_ID = os.getenv('CLICKUP_LIST_ID', '')
    CLICKUP_TEAM_ID = os.getenv('CLICKUP_TEAM_ID', '')

    # Diretórios
    PDF_UPLOAD_DIR = Path('uploads/pdfs')
    EMAIL_ATTACHMENTS_DIR = Path('uploads/email_attachments')
    REPORTS_DIR = Path('reports')

    # Criar diretórios se não existirem
    PDF_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EMAIL_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ========================================
# MODELOS DO BANCO DE DADOS (PostgreSQL)
# ========================================


Base = declarative_base()


class Email(Base):
    """Modelo para e-mails"""
    __tablename__ = 'emails'

    id = Column(String(255), primary_key=True)
    subject = Column(Text)
    sender = Column(String(255))
    received_date = Column(DateTime)
    body_preview = Column(Text)
    body_full = Column(Text)
    priority = Column(String(50))
    has_attachments = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    clickup_task_id = Column(String(255), nullable=True)
    metadata = Column(JSON)  # Dados adicionais flexíveis
    created_at = Column(DateTime, default=datetime.now)
    processed = Column(Boolean, default=False)


class Attachment(Base):
    """Modelo para anexos de e-mail"""
    __tablename__ = 'attachments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_id = Column(String(255))
    filename = Column(String(255))
    content_type = Column(String(100))
    size = Column(Integer)
    file_path = Column(String(500))
    extracted_data = Column(JSON)  # Dados extraídos do anexo
    created_at = Column(DateTime, default=datetime.now)


class Valve(Base):
    """Modelo para informações de válvulas extraídas de PDFs"""
    __tablename__ = 'valves'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Informações básicas
    tag = Column(String(100))
    description = Column(Text)
    manufacturer = Column(String(255))
    model = Column(String(255))
    serial_number = Column(String(255))

    # Especificações técnicas
    valve_type = Column(String(100))  # Globo, Esfera, Gaveta, etc.
    size = Column(String(50))  # Tamanho nominal
    pressure_rating = Column(String(50))  # Classe de pressão
    material = Column(String(255))
    connection_type = Column(String(100))

    # Atuador
    actuator_type = Column(String(100))  # Pneumático, Elétrico, Manual
    actuator_manufacturer = Column(String(255))
    actuator_model = Column(String(255))

    # Posicionador
    positioner_manufacturer = Column(String(255))
    positioner_model = Column(String(255))

    # Dados operacionais
    cv_value = Column(Float)  # Coeficiente de vazão
    operating_pressure = Column(Float)
    operating_temperature = Column(Float)

    # Rastreabilidade
    source_file = Column(String(500))  # Caminho do PDF original
    email_id = Column(String(255), nullable=True)  # Se veio de e-mail
    clickup_task_id = Column(String(255), nullable=True)

    # Dados adicionais flexíveis
    additional_data = Column(JSON)

    # Controle
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    status = Column(String(50), default='active')  # active, inactive, maintenance


class ClickUpTask(Base):
    """Modelo para tarefas do ClickUp"""
    __tablename__ = 'clickup_tasks'

    id = Column(String(255), primary_key=True)
    name = Column(Text)
    description = Column(Text)
    status = Column(String(100))
    priority = Column(Integer)
    due_date = Column(DateTime, nullable=True)
    email_id = Column(String(255), nullable=True)
    valve_id = Column(Integer, nullable=True)
    assignees = Column(JSON)
    tags = Column(JSON)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SyncLog(Base):
    """Modelo para logs de sincronização"""
    __tablename__ = 'sync_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(String(50))  # email, pdf, clickup
    sync_date = Column(DateTime, default=datetime.now)
    items_processed = Column(Integer)
    items_success = Column(Integer)
    items_failed = Column(Integer)
    status = Column(String(50))
    error_message = Column(Text, nullable=True)
    metadata = Column(JSON)


# ========================================
# DATABASE MANAGER
# ========================================


class DatabaseManager:
    """Gerenciador centralizado do banco de dados"""

    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.create_tables()
        logger.info("✅ Database Manager inicializado")

    def create_tables(self):
        """Criar todas as tabelas"""
        Base.metadata.create_all(self.engine)
        logger.info("✅ Tabelas criadas/verificadas no PostgreSQL")

    def get_session(self) -> Session:
        """Obter sessão do banco"""
        return self.SessionLocal()

    def save_email(self, email_data: Dict) -> Email:
        """Salvar e-mail no banco"""
        session = self.get_session()
        try:
            email = Email(**email_data)
            session.merge(email)  # merge atualiza se existir
            session.commit()
            logger.info(f"✅ E-mail salvo: {email.id}")
            return email
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro ao salvar e-mail: {e}")
            raise
        finally:
            session.close()

    def save_valve(self, valve_data: Dict) -> Valve:
        """Salvar válvula no banco"""
        session = self.get_session()
        try:
            valve = Valve(**valve_data)
            session.add(valve)
            session.commit()
            session.refresh(valve)
            logger.info(f"✅ Válvula salva: ID {valve.id} - TAG {valve.tag}")
            return valve
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro ao salvar válvula: {e}")
            raise
        finally:
            session.close()

    def save_clickup_task(self, task_data: Dict) -> ClickUpTask:
        """Salvar tarefa do ClickUp"""
        session = self.get_session()
        try:
            task = ClickUpTask(**task_data)
            session.merge(task)
            session.commit()
            logger.info(f"✅ Tarefa ClickUp salva: {task.id}")
            return task
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro ao salvar tarefa: {e}")
            raise
        finally:
            session.close()

    def log_sync(self, log_data: Dict):
        """Registrar log de sincronização"""
        session = self.get_session()
        try:
            log = SyncLog(**log_data)
            session.add(log)
            session.commit()
            logger.info(f"✅ Log registrado: {log.sync_type}")
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro ao registrar log: {e}")
        finally:
            session.close()


# ========================================
# OUTLOOK INTEGRATION
# ========================================


class OutlookIntegration:
    """Integração com Outlook 365"""

    def __init__(self, client_id: str, client_secret: str, tenant_id: str, user_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.access_token = None
        self.graph_url = "https://graph.microsoft.com/v1.0"
        logger.info("✅ Outlook Integration inicializado")

    def authenticate(self) -> bool:
        """Autenticar no Outlook"""
        try:
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=authority,
                client_credential=self.client_secret
            )

            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )

            if "access_token" in result:
                self.access_token = result['access_token']
                logger.info("✅ Autenticação Outlook bem-sucedida")
                return True
            else:
                logger.error(f"❌ Falha na autenticação: {result.get('error_description')}")
                return False
        except Exception as e:
            logger.error(f"❌ Erro na autenticação: {e}")
            return False

    def get_emails(self, top: int = 50, filter_date: Optional[datetime] = None) -> List[Dict]:
        """Buscar e-mails"""
        if not self.access_token:
            logger.error("❌ Não autenticado")
            return []

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        if not self.user_id:
            logger.error("❌ ID do usuário do Outlook não configurado")
            return []

        url = f"{self.graph_url}/users/{self.user_id}/messages"
        params = {
            '$top': top,
            '$select': 'id,subject,from,receivedDateTime,bodyPreview,body,hasAttachments,isRead',
            '$orderby': 'receivedDateTime DESC'
        }

        if filter_date:
            params['$filter'] = f"receivedDateTime ge {filter_date.isoformat()}"

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            emails = response.json().get('value', [])
            logger.info(f"✅ {len(emails)} e-mails recuperados")
            return emails
        except Exception as e:
            logger.error(f"❌ Erro ao buscar e-mails: {e}")
            return []

    def get_attachments(self, email_id: str) -> List[Dict]:
        """Buscar anexos de um e-mail"""
        if not self.access_token:
            return []

        if not self.user_id:
            logger.error("❌ ID do usuário do Outlook não configurado")
            return []

        headers = {'Authorization': f'Bearer {self.access_token}'}
        url = f"{self.graph_url}/users/{self.user_id}/messages/{email_id}/attachments"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get('value', [])
        except Exception as e:
            logger.error(f"❌ Erro ao buscar anexos: {e}")
            return []

    def download_attachment(self, email_id: str, attachment_id: str, save_path: Path) -> bool:
        """Baixar anexo"""
        if not self.access_token:
            return False

        if not self.user_id:
            logger.error("❌ ID do usuário do Outlook não configurado")
            return False

        headers = {'Authorization': f'Bearer {self.access_token}'}
        url = f"{self.graph_url}/users/{self.user_id}/messages/{email_id}/attachments/{attachment_id}"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            att_data = response.json()
            content_bytes = att_data.get('contentBytes', '')

            if content_bytes:
                import base64
                with open(save_path, 'wb') as f:
                    f.write(base64.b64decode(content_bytes))
                logger.info(f"✅ Anexo baixado: {save_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Erro ao baixar anexo: {e}")

        return False


# ========================================
# CLICKUP INTEGRATION
# ========================================


class ClickUpIntegration:
    """Integração com ClickUp"""

    def __init__(self, api_key: str, list_id: str):
        self.api_key = api_key
        self.list_id = list_id
        self.base_url = "https://api.clickup.com/api/v2"
        self.headers = {
            'Authorization': api_key,
            'Content-Type': 'application/json'
        }
        logger.info("✅ ClickUp Integration inicializado")

    def create_task(self, title: str, description: str, priority: str = 'normal',
                    due_date: Optional[datetime] = None, tags: List[str] = None) -> Optional[Dict]:
        """Criar tarefa no ClickUp"""

        priority_map = {'urgent': 1, 'high': 2, 'normal': 3, 'low': 4}

        task_data = {
            'name': title,
            'description': description,
            'priority': priority_map.get(priority.lower(), 3),
            'status': 'to do'
        }

        if due_date:
            task_data['due_date'] = int(due_date.timestamp() * 1000)

        if tags:
            task_data['tags'] = tags

        url = f"{self.base_url}/list/{self.list_id}/task"

        try:
            response = requests.post(url, headers=self.headers, json=task_data)
            response.raise_for_status()
            task = response.json()
            logger.info(f"✅ Tarefa ClickUp criada: {task.get('id')}")
            return task
        except Exception as e:
            logger.error(f"❌ Erro ao criar tarefa: {e}")
            return None


# ========================================
# PDF EXTRACTOR (VÁLVULAS)
# ========================================


class ValvePDFExtractor:
    """Extrator especializado para PDFs de válvulas"""

    def __init__(self):
        logger.info("✅ Valve PDF Extractor inicializado")

    def extract_from_pdf(self, pdf_path: Path) -> Dict:
        """Extrair informações de válvulas de PDF"""
        logger.info(f"📄 Processando PDF: {pdf_path}")

        valve_data = {
            'source_file': str(pdf_path),
            'additional_data': {}
        }

        try:
            # Extrair texto completo
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                full_text = ""
                for page in pdf_reader.pages:
                    full_text += page.extract_text()

            # Buscar padrões comuns em datasheets de válvulas
            valve_data.update(self._parse_valve_info(full_text))

            # Tentar extrair tabelas
            tables = self._extract_tables(pdf_path)
            if tables:
                valve_data['additional_data']['tables'] = tables

            logger.info(f"✅ Dados extraídos do PDF: TAG {valve_data.get('tag', 'N/A')}")
            return valve_data

        except Exception as e:
            logger.error(f"❌ Erro ao processar PDF: {e}")
            return valve_data

    def _parse_valve_info(self, text: str) -> Dict:
        """Parsear informações de válvula do texto"""
        import re

        info = {}

        # Padrões de busca (exemplos - ajuste conforme seus PDFs)
        patterns = {
            'tag': r'TAG[:\s]+([A-Z0-9\-]+)',
            'model': r'MODEL[:\s]+([A-Z0-9\-]+)',
            'serial_number': r'S/?N[:\s]+([A-Z0-9\-]+)',
            'size': r'SIZE[:\s]+(\d+[\s"]?[A-Z]*)',
            'manufacturer': r'MANUFACTURER[:\s]+([A-Z\s&]+)',
            'pressure_rating': r'CLASS[:\s]+(\d+)',
            'valve_type': r'TYPE[:\s]+(GLOBE|BALL|GATE|BUTTERFLY|CHECK)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info[key] = match.group(1).strip()

        return info

    def _extract_tables(self, pdf_path: Path) -> List[Dict]:
        """Extrair tabelas do PDF"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                tables = []
                for page in pdf.pages:
                    page_tables = page.extract_tables()
                    if page_tables:
                        tables.extend(page_tables)
                return tables
        except Exception as e:
            logger.error(f"⚠️ Erro ao extrair tabelas: {e}")
            return []


# ========================================
# ORCHESTRATOR (ORQUESTRADOR PRINCIPAL)
# ========================================


class Orchestrator:
    """Orquestrador central que coordena todas as integrações"""

    def __init__(self):
        logger.info("="*60)
        logger.info("🎯 INICIALIZANDO ORQUESTRADOR CENTRAL")
        logger.info("="*60)

        # Inicializar componentes
        self.db = DatabaseManager(Config.DATABASE_URL)
        self.outlook = OutlookIntegration(
            Config.OUTLOOK_CLIENT_ID,
            Config.OUTLOOK_CLIENT_SECRET,
            Config.OUTLOOK_TENANT_ID,
            Config.OUTLOOK_USER_ID
        )
        self.clickup = ClickUpIntegration(
            Config.CLICKUP_API_KEY,
            Config.CLICKUP_LIST_ID
        )
        self.pdf_extractor = ValvePDFExtractor()

        logger.info("✅ Todos os componentes inicializados")

    def sync_emails(self, days_back: int = 7) -> Dict:
        """Sincronizar e-mails do Outlook"""
        logger.info(f"📧 Iniciando sincronização de e-mails (últimos {days_back} dias)")

        stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'with_attachments': 0,
            'valves_found': 0
        }

        # Autenticar
        if not self.outlook.authenticate():
            logger.error("❌ Falha na autenticação do Outlook")
            return stats

        # Buscar e-mails
        filter_date = datetime.now() - timedelta(days=days_back)
        emails = self.outlook.get_emails(top=100, filter_date=filter_date)
        stats['total'] = len(emails)

        for email in emails:
            try:
                # Processar e-mail
                email_data = self._process_email(email)
                self.db.save_email(email_data)
                stats['success'] += 1

                # Processar anexos
                if email.get('hasAttachments'):
                    stats['with_attachments'] += 1
                    valves = self._process_email_attachments(email['id'])
                    stats['valves_found'] += len(valves)

            except Exception as e:
                logger.error(f"❌ Erro ao processar e-mail {email.get('id')}: {e}")
                stats['failed'] += 1

        # Registrar log
        self.db.log_sync({
            'sync_type': 'email',
            'items_processed': stats['total'],
            'items_success': stats['success'],
            'items_failed': stats['failed'],
            'status': 'completed',
            'metadata': stats
        })

        logger.info(f"✅ Sincronização de e-mails concluída: {stats}")
        return stats

    def _process_email(self, email: Dict) -> Dict:
        """Processar dados do e-mail"""
        return {
            'id': email['id'],
            'subject': email.get('subject', ''),
            'sender': email.get('from', {}).get('emailAddress', {}).get('address', ''),
            'received_date': datetime.fromisoformat(email['receivedDateTime'].replace('Z', '+00:00')),
            'body_preview': email.get('bodyPreview', ''),
            'body_full': email.get('body', {}).get('content', ''),
            'priority': self._analyze_priority(email.get('subject', ''), email.get('isRead', True)),
            'has_attachments': email.get('hasAttachments', False),
            'is_read': email.get('isRead', False),
            'metadata': {
                'importance': email.get('importance', 'normal'),
                'categories': email.get('categories', [])
            }
        }

    def _analyze_priority(self, subject: str, is_read: bool) -> str:
        """Analisar prioridade do e-mail"""
        subject_lower = subject.lower()

        urgent_keywords = ['urgente', 'urgent', 'asap', 'crítico', 'emergency']
        high_keywords = ['importante', 'prioridade', 'deadline', 'prazo']

        if any(kw in subject_lower for kw in urgent_keywords):
            return 'urgent'
        elif any(kw in subject_lower for kw in high_keywords) or not is_read:
            return 'high'
        else:
            return 'normal'

    def _process_email_attachments(self, email_id: str) -> List[Valve]:
        """Processar anexos de e-mail e extrair informações de válvulas"""
        attachments = self.outlook.get_attachments(email_id)
        valves = []

        for att in attachments:
            # Verificar se é PDF
            if att.get('contentType') == 'application/pdf' or att['name'].lower().endswith('.pdf'):
                # Baixar anexo
                save_path = Config.EMAIL_ATTACHMENTS_DIR / f"{email_id}_{att['name']}"

                if self.outlook.download_attachment(email_id, att['id'], save_path):
                    # Salvar registro do anexo
                    session = self.db.get_session()
                    try:
                        attachment = Attachment(
                            email_id=email_id,
                            filename=att['name'],
                            content_type=att.get('contentType'),
                            size=att.get('size'),
                            file_path=str(save_path)
                        )
                        session.add(attachment)
                        session.commit()
                    finally:
                        session.close()

                    # Extrair dados de válvula
                    valve_data = self.pdf_extractor.extract_from_pdf(save_path)
                    valve_data['email_id'] = email_id

                    valve = self.db.save_valve(valve_data)
                    valves.append(valve)

        return valves

    def process_pdf_folder(self, folder_path: Path) -> Dict:
        """Processar pasta com PDFs de válvulas"""
        logger.info(f"📁 Processando PDFs na pasta: {folder_path}")

        stats = {'total': 0, 'success': 0, 'failed': 0}

        pdf_files = list(folder_path.glob('*.pdf'))
        stats['total'] = len(pdf_files)

        for pdf_file in pdf_files:
            try:
                valve_data = self.pdf_extractor.extract_from_pdf(pdf_file)
                self.db.save_valve(valve_data)
                stats['success'] += 1
            except Exception as e:
                logger.error(f"❌ Erro ao processar {pdf_file}: {e}")
                stats['failed'] += 1

        logger.info(f"✅ Processamento de PDFs concluído: {stats}")
        return stats

    def create_valve_tasks(self, valve_status: str = 'active') -> Dict:
        """Criar tarefas no ClickUp para válvulas que precisam de atenção"""
        logger.info(f"✅ Criando tarefas para válvulas com status: {valve_status}")

        session = self.db.get_session()
        try:
            valves = session.query(Valve).filter(
                Valve.status == valve_status,
                Valve.clickup_task_id == None
            ).all()

            stats = {'total': len(valves), 'created': 0, 'failed': 0}

            for valve in valves:
                try:
                    task_title = f"Válvula {valve.tag or 'S/N'} - {valve.description or 'Verificação'}"
                    task_desc = f"""
**TAG:** {valve.tag or 'N/A'}
**Fabricante:** {valve.manufacturer or 'N/A'}
**Modelo:** {valve.model or 'N/A'}
**Tipo:** {valve.valve_type or 'N/A'}
**Tamanho:** {valve.size or 'N/A'}
**Arquivo:** {valve.source_file}
                    """.strip()

                    task = self.clickup.create_task(
                        title=task_title,
                        description=task_desc,
                        priority='normal',
                        tags=['válvula', 'manutenção']
                    )

                    if task:
                        valve.clickup_task_id = task['id']
                        session.commit()

                        # Salvar no banco
                        self.db.save_clickup_task({
                            'id': task['id'],
                            'name': task['name'],
                            'description': task_desc,
                            'status': 'to do',
                            'priority': 3,
                            'valve_id': valve.id
                        })

                        stats['created'] += 1

                except Exception as e:
                    logger.error(f"❌ Erro ao criar tarefa para válvula {valve.id}: {e}")
                    stats['failed'] += 1

            logger.info(f"✅ Tarefas criadas: {stats}")
            return stats
        finally:
            session.close()

    def generate_report(self) -> pd.DataFrame:
        """Gerar relatório consolidado"""
        logger.info("📊 Gerando relatório consolidado")

        session = self.db.get_session()
        try:
            emails_df = pd.read_sql(session.query(Email).statement, session.bind)
            valves_df = pd.read_sql(session.query(Valve).statement, session.bind)
            tasks_df = pd.read_sql(session.query(ClickUpTask).statement, session.bind)

            report = {
                'emails_total': len(emails_df),
                'emails_processados': emails_df['processed'].sum() if 'processed' in emails_df else 0,
                'valvulas_total': len(valves_df),
                'tarefas_total': len(tasks_df)
            }

            logger.info(f"✅ Relatório gerado: {report}")

            report_df = pd.DataFrame([report])
            report_file = Config.REPORTS_DIR / f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            report_df.to_excel(report_file, index=False)

            logger.info(f"✅ Relatório salvo em: {report_file}")
            return report_df
        finally:
            session.close()

    def run_full_sync(self):
        """Executar sincronização completa"""
        logger.info("🚀 Iniciando sincronização completa")

        email_stats = self.sync_emails()
        pdf_stats = self.process_pdf_folder(Config.PDF_UPLOAD_DIR)
        task_stats = self.create_valve_tasks()
        report_df = self.generate_report()

        summary = {
            'emails': email_stats,
            'pdfs': pdf_stats,
            'tasks': task_stats,
            'report': report_df.to_dict(orient='records')[0] if not report_df.empty else {}
        }

        logger.info(f"✅ Sincronização completa concluída: {summary}")
        return summary


if __name__ == '__main__':
    orchestrator = Orchestrator()
    orchestrator.run_full_sync()
