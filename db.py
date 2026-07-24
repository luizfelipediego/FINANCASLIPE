# -*- coding: utf-8 -*-
"""
db.py
=====
Camada de acesso a dados do Sistema de Gestão Financeira Pessoal e Familiar.

CORREÇÕES NESTA VERSÃO:
- execute()/fetch_all()/fetch_one() agora SEMPRE convertem params para tupla
  antes de chamar conn.execute(). O driver 'libsql' (usado no backend Turso/nuvem)
  é mais rígido que o sqlite3 padrão e lança ValueError quando recebe uma lista
  no lugar de uma tupla — essa era a causa do erro em todas as páginas.
- Adicionada coluna 'banco' na tabela cartoes (migração automática e segura).
- add_cartao() agora aceita o parâmetro 'banco'.

Alterações da versão anterior (mantidas):
- Tabela users para login (email + password_hash + is_admin).
- Proteção: admins NÃO podem ver dados pessoais/financeiros de outros usuários por padrão.
- audit_logs para histórico (before/after em JSON).
- user_id em tabelas principais (receitas, despesas, despesas_fixas, categorias, cartoes).
- Funções de criação/autenticação de usuário (bcrypt).
- Funções de edição/exclusão que gravam audit_logs.
- Backup local simples do arquivo SQLite.
- Envio de e-mail opcional (SMTP) para notificações (configurar variáveis de ambiente).
"""

import os
import sys
import sqlite3
import uuid
import calendar
import json
import traceback
from datetime import date, datetime
from shutil import copy2

DB_PATH = "financas.db"
BACKUP_DIR = "backups"

# ---------------------------------------------------------------------------
# Dependências opcionais (bcrypt para senhas). Instalar: pip install bcrypt
# ---------------------------------------------------------------------------
try:
    import bcrypt
except Exception:
    bcrypt = None

# ---------------------------------------------------------------------------
# Configuração de credenciais (Turso / nuvem) e seleção automática de backend
# ---------------------------------------------------------------------------

def _get_secret(key: str):
    """Busca uma credencial em st.secrets (Streamlit Cloud) e, senão, em variáveis de ambiente."""
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key)


def usando_banco_em_nuvem() -> bool:
    """Retorna True se as credenciais do Turso estiverem configuradas."""
    return bool(_get_secret("TURSO_DATABASE_URL")) and bool(_get_secret("TURSO_AUTH_TOKEN"))


def get_backend_info() -> str:
    """Texto amigável indicando qual backend de banco está ativo (para exibir na UI)."""
    if usando_banco_em_nuvem():
        return "☁️ Turso (nuvem) — dados persistentes, não se perdem em reinícios"
    return "💻 SQLite local (financas.db) — ideal para uso/teste na sua máquina"


def _nova_conexao():
    """Abre uma conexão nova (nuvem ou local). Deve ser fechada logo após o uso."""
    if usando_banco_em_nuvem():
        import libsql
        return libsql.connect(
            database=_get_secret("TURSO_DATABASE_URL"),
            auth_token=_get_secret("TURSO_AUTH_TOKEN"),
        )
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except Exception:
        pass
    return conn


def _erro_de_stream_expirado(exc: Exception) -> bool:
    """Detecta o erro conhecido do Turso/Hrana de conexão (stream) expirada."""
    msg = str(exc).lower()
    return "stream not found" in msg or "stream_not_found" in msg or ("hrana" in msg and "404" in msg)


def _params_para_tupla(params):
    """Normaliza os parâmetros de uma query para tupla (formato mais universal)."""
    if params is None:
        return ()
    if isinstance(params, tuple):
        return params
    return tuple(params)


def _log_erro_diagnostico(sql, params, tentativa_formato, exc):
    """
    Registra no console (stdout/stderr) todos os detalhes do erro.
    Isso aparece nos LOGS do Streamlit Cloud (botão 'Manage app' -> 'Logs'),
    mesmo quando a interface mostra a mensagem redigida/oculta por segurança.
    """
    print("=" * 80, file=sys.stderr)
    print("[DB DEBUG] Falha ao executar SQL", file=sys.stderr)
    print(f"[DB DEBUG] SQL: {sql}", file=sys.stderr)
    print(f"[DB DEBUG] Params ({tentativa_formato}): {params!r}", file=sys.stderr)
    print(f"[DB DEBUG] Tipos dos params: {[type(p).__name__ for p in params] if params else '[]'}", file=sys.stderr)
    print(f"[DB DEBUG] Backend em nuvem (Turso)? {usando_banco_em_nuvem()}", file=sys.stderr)
    print(f"[DB DEBUG] Exceção: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)
    print("=" * 80, file=sys.stderr)


def _executar_com_fallback(conn, sql, params):
    """
    Executa a query tentando, em ordem, os formatos de parâmetro mais comuns
    aceitos por diferentes drivers (sqlite3 local e libsql/Turso na nuvem):
      1) params como tupla (padrão)
      2) params como lista
      3) sem nenhum parâmetro (quando a tupla está vazia)
    Se todas as tentativas falharem, relança a ÚLTIMA exceção capturada,
    após registrar detalhes de diagnóstico nos logs do servidor.
    """
    params = _params_para_tupla(params)

    tentativas = [("tupla", params)]
    tentativas.append(("lista", list(params)))
    if len(params) == 0:
        tentativas.append(("sem_params", None))

    ultima_excecao = None
    for nome_formato, params_tentativa in tentativas:
        try:
            if params_tentativa is None:
                return conn.execute(sql)
            return conn.execute(sql, params_tentativa)
        except Exception as e:
            ultima_excecao = e
            _log_erro_diagnostico(sql, params, nome_formato, e)
            continue
    raise ultima_excecao


# ---------------------------------------------------------------------------
# Helpers para converter resultados de query em dicionários
# ---------------------------------------------------------------------------

def _rows_to_dicts(cursor, rows):
    if not rows:
        return []
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in rows]


def _row_to_dict(cursor, row):
    if row is None:
        return None
    cols = [c[0] for c in cursor.description]
    return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# Primitivas de execução (cada operação abre/fecha conexão)
# ---------------------------------------------------------------------------

def execute(sql: str, params=()):
    """Executa um INSERT/UPDATE/DELETE isolado (não retorna dados)."""
    ultima_excecao = None
    for tentativa in range(2):
        conn = _nova_conexao()
        try:
            _executar_com_fallback(conn, sql, params)
            conn.commit()
            return
        except Exception as e:
            ultima_excecao = e
            if tentativa == 0 and _erro_de_stream_expirado(e):
                continue
            raise
        finally:
            conn.close()
    raise ultima_excecao


def fetch_all(sql: str, params=()) -> list:
    """Executa um SELECT isolado e retorna uma lista de dicts."""
    ultima_excecao = None
    for tentativa in range(2):
        conn = _nova_conexao()
        try:
            cur = _executar_com_fallback(conn, sql, params)
            return _rows_to_dicts(cur, cur.fetchall())
        except Exception as e:
            ultima_excecao = e
            if tentativa == 0 and _erro_de_stream_expirado(e):
                continue
            raise
        finally:
            conn.close()
    raise ultima_excecao


def fetch_one(sql: str, params=()):
    """Executa um SELECT isolado e retorna um único dict (ou None)."""
    ultima_excecao = None
    for tentativa in range(2):
        conn = _nova_conexao()
        try:
            cur = _executar_com_fallback(conn, sql, params)
            return _row_to_dict(cur, cur.fetchone())
        except Exception as e:
            ultima_excecao = e
            if tentativa == 0 and _erro_de_stream_expirado(e):
                continue
            raise
        finally:
            conn.close()
    raise ultima_excecao


# ---------------------------------------------------------------------------
# Utilitários de data
# ---------------------------------------------------------------------------

def add_months(d: date, months: int) -> date:
    """Soma (ou subtrai) meses a uma data, ajustando o dia se o mês destino for mais curto."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_key(d: date) -> str:
    """Retorna o primeiro dia do mês em formato YYYY-MM-DD (usado como 'data_competencia')."""
    return date(d.year, d.month, 1).isoformat()


# ---------------------------------------------------------------------------
# Auditoria / backup / e segurança
# ---------------------------------------------------------------------------

def log_action(user_id, action, table_name, row_id=None, before=None, after=None):
    """Registra histórico em audit_logs (before/after em JSON)."""
    execute("""
        INSERT INTO audit_logs
        (user_id, action, table_name, row_id, before_json, after_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        action,
        table_name,
        row_id,
        json.dumps(before, default=str) if before is not None else None,
        json.dumps(after, default=str) if after is not None else None
    ))


def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def backup_db():
    """Copia o arquivo SQLite local para backups/ com timestamp. Retorna caminho do backup ou None."""
    if usando_banco_em_nuvem():
        # Para Turso, backup exige outro fluxo (export via API) — não implementado aqui.
        return None
    ensure_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    src = DB_PATH
    dst = os.path.join(BACKUP_DIR, f"financas-{timestamp}.db")
    copy2(src, dst)
    return dst


# Envio de e-mail simples (opcional). Configurar SMTP via variáveis/ st.secrets:
# SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
def send_email(to_email: str, subject: str, body: str):
    host = _get_secret("SMTP_HOST")
    port = int(_get_secret("SMTP_PORT") or 587)
    user = _get_secret("SMTP_USER")
    passwd = _get_secret("SMTP_PASS")
    if not (host and user and passwd):
        raise RuntimeError("SMTP não configurado nas variáveis de ambiente/st.secrets")
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    import smtplib
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, passwd)
        s.send_message(msg)


# ---------------------------------------------------------------------------
# Inicialização do schema (adiciona users, audit_logs, colunas user_id e banco)
# ---------------------------------------------------------------------------

def _coluna_existe(tabela: str, coluna: str) -> bool:
    """Verifica se uma coluna já existe em uma tabela (via PRAGMA table_info)."""
    try:
        info = fetch_all(f"PRAGMA table_info({tabela})")
        return any(c.get("name") == coluna for c in info)
    except Exception:
        return False


def _garantir_coluna(tabela: str, coluna: str, definicao_sql: str):
    """Adiciona uma coluna à tabela caso ela ainda não exista (migração segura)."""
    if not _coluna_existe(tabela, coluna):
        try:
            execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao_sql}")
        except Exception:
            # Se outra sessão já adicionou a coluna simultaneamente, ignora.
            pass


def init_db():
    """Cria todas as tabelas do sistema, caso ainda não existam (cada instrução isolada)."""
    # tabelas originais (mantendo seu schema)
    execute("""
    CREATE TABLE IF NOT EXISTS categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        teto_mensal REAL DEFAULT 0,
        user_id INTEGER DEFAULT NULL
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS cartoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        dia_fechamento INTEGER NOT NULL,
        dia_vencimento INTEGER NOT NULL,
        user_id INTEGER DEFAULT NULL
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS receitas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        origem TEXT NOT NULL,
        valor REAL NOT NULL,
        observacao TEXT,
        user_id INTEGER DEFAULT NULL
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS despesas_fixas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descricao TEXT NOT NULL,
        categoria_id INTEGER,
        valor REAL NOT NULL,
        forma_pagamento TEXT NOT NULL,
        cartao_id INTEGER,
        dia_vencimento INTEGER DEFAULT 1,
        ativa INTEGER DEFAULT 1,
        user_id INTEGER DEFAULT NULL,
        FOREIGN KEY (categoria_id) REFERENCES categorias(id),
        FOREIGN KEY (cartao_id) REFERENCES cartoes(id)
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS despesas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_compra TEXT NOT NULL,
        data_competencia TEXT NOT NULL,
        categoria_id INTEGER,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        forma_pagamento TEXT NOT NULL,
        cartao_id INTEGER,
        parcela_atual INTEGER DEFAULT 1,
        parcela_total INTEGER DEFAULT 1,
        compra_grupo TEXT,
        fixa INTEGER DEFAULT 0,
        fixa_origem_id INTEGER,
        user_id INTEGER DEFAULT NULL,
        FOREIGN KEY (categoria_id) REFERENCES categorias(id),
        FOREIGN KEY (cartao_id) REFERENCES cartoes(id),
        FOREIGN KEY (fixa_origem_id) REFERENCES despesas_fixas(id)
    )
    """)

    execute("""
    CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY,
        reserva_percentual REAL DEFAULT 10
    )
    """)
    execute("INSERT OR IGNORE INTO config (id, reserva_percentual) VALUES (1, 10)")

    # Tabela de usuários
    execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)

    # Tabela de auditoria / histórico
    execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        table_name TEXT NOT NULL,
        row_id INTEGER,
        before_json TEXT,
        after_json TEXT,
        timestamp TEXT DEFAULT (datetime('now'))
    )
    """)

    # Migração: coluna 'banco' na tabela cartoes (para o seletor com emoji do banco)
    _garantir_coluna("cartoes", "banco", "TEXT DEFAULT NULL")

    # Se o banco for novo, popula categorias padrão (sem user_id)
    total_categorias_row = fetch_one("SELECT COUNT(*) AS n FROM categorias")
    total_categorias = total_categorias_row["n"] if total_categorias_row else 0
    if total_categorias == 0:
        padrao = ["Mercado", "Saúde/Remédios", "Estudos/Educação",
                  "Lazer", "Moradia", "Veículo", "Outros"]
        for nome in padrao:
            execute("INSERT INTO categorias (nome, teto_mensal) VALUES (?, 0)", (nome,))

    # Garante diretório de backups
    ensure_backup_dir()


# ---------------------------------------------------------------------------
# Segurança: hashing de senha e CRUD de usuários
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    if bcrypt is None:
        raise RuntimeError("bcrypt não instalado. Rode: pip install bcrypt")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    if bcrypt is None:
        raise RuntimeError("bcrypt não instalado. Rode: pip install bcrypt")
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_user(email: str, password: str, is_admin: bool = False):
    """Cria usuário. Retorna o id do usuário recém-criado."""
    senha_hash = _hash_password(password)
    execute("INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)",
            (email.strip().lower(), senha_hash, 1 if is_admin else 0))
    row = fetch_one("SELECT id FROM users WHERE email = ?", (email.strip().lower(),))
    return row["id"] if row else None


def get_user_by_email(email: str):
    return fetch_one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))


def get_user_by_id(user_id: int):
    return fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


def authenticate_user(email: str, password: str):
    u = get_user_by_email(email)
    if not u:
        return None
    if _verify_password(password, u["password_hash"]):
        # Remove password_hash when returning user object to UI
        u_safe = {k: v for k, v in u.items() if k != "password_hash"}
        return u_safe
    return None


def set_user_password(user_id: int, new_password: str):
    execute("UPDATE users SET password_hash = ? WHERE id = ?", (_hash_password(new_password), user_id))


def create_initial_admin(email: str, password: str, send_email_flag: bool = False):
    """
    Cria um administrador inicial. Se send_email_flag=True e SMTP configurado,
    envia as credenciais por e-mail (atenção: inseguro enviar senha em texto).
    """
    admin_id = create_user(email, password, is_admin=True)
    if send_email_flag:
        try:
            body = f"Suas credenciais:\nEmail: {email}\nSenha: {password}\nTroque a senha ao entrar."
            send_email(email, "Acesso de administrador", body)
        except Exception as e:
            # não falha criação por erro de e-mail
            print("Falha ao enviar e-mail:", e)
    return admin_id


# ---------------------------------------------------------------------------
# Regras de acesso (PRIVACIDADE): admins NÃO podem ver dados dos usuários
# ---------------------------------------------------------------------------

def _can_access_record(requesting_user, record_user_id) -> bool:
    """
    Política: apenas o dono pode ver seus próprios registros.
    Mesmo admins NÃO têm acesso aos registros de outros usuários por padrão,
    conforme solicitado.
    """
    if requesting_user is None:
        return False
    if requesting_user.get("id") == record_user_id:
        return True
    # não permitir admin ver outros usuários por padrão
    return False


# ---------------------------------------------------------------------------
# Categorias (user-aware)
# ---------------------------------------------------------------------------

def add_categoria(nome: str, teto_mensal: float = 0.0, user_id: int = None):
    execute("INSERT INTO categorias (nome, teto_mensal, user_id) VALUES (?, ?, ?)",
            (nome.strip(), teto_mensal, user_id))


def list_categorias(requesting_user: dict = None):
    """
    Lista categorias VISÍVEIS para requesting_user:
    - categorias com user_id IS NULL (padrão/global)
    - categorias com user_id == requesting_user.id
    """
    params = []
    sql = "SELECT * FROM categorias WHERE (user_id IS NULL)"
    if requesting_user:
        sql += " OR user_id = ?"
        params.append(requesting_user.get("id"))
    sql += " ORDER BY nome"
    return fetch_all(sql, params)


def update_categoria_teto(categoria_id: int, teto_mensal: float, requesting_user: dict):
    before = fetch_one("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para alterar esta categoria.")
    execute("UPDATE categorias SET teto_mensal = ? WHERE id = ?", (teto_mensal, categoria_id))
    after = fetch_one("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    log_action(requesting_user.get("id"), "UPDATE", "categorias", categoria_id, before, after)


def delete_categoria(categoria_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir esta categoria.")
    execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
    log_action(requesting_user.get("id"), "DELETE", "categorias", categoria_id, before, None)


# ---------------------------------------------------------------------------
# Cartões de crédito (user-aware)
# ---------------------------------------------------------------------------

def add_cartao(nome: str, dia_fechamento: int, dia_vencimento: int, banco: str = None, user_id: int = None):
    execute("INSERT INTO cartoes (nome, dia_fechamento, dia_vencimento, banco, user_id) VALUES (?, ?, ?, ?, ?)",
            (nome.strip(), dia_fechamento, dia_vencimento, banco, user_id))


def list_cartoes(requesting_user: dict = None):
    params = []
    sql = "SELECT * FROM cartoes WHERE (user_id IS NULL)"
    if requesting_user:
        sql += " OR user_id = ?"
        params.append(requesting_user.get("id"))
    sql += " ORDER BY nome"
    return fetch_all(sql, params)


def delete_cartao(cartao_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM cartoes WHERE id = ?", (cartao_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir este cartão.")
    execute("DELETE FROM cartoes WHERE id = ?", (cartao_id,))
    log_action(requesting_user.get("id"), "DELETE", "cartoes", cartao_id, before, None)


# ---------------------------------------------------------------------------
# Receitas (entradas) - user-aware
# ---------------------------------------------------------------------------

def add_receita(data_str: str, origem: str, valor: float, observacao: str = "", user_id: int = None):
    execute("INSERT INTO receitas (data, origem, valor, observacao, user_id) VALUES (?, ?, ?, ?, ?)",
            (data_str, origem, valor, observacao, user_id))
    # log
    row = fetch_one("SELECT * FROM receitas WHERE id = (SELECT last_insert_rowid())")
    log_action(user_id, "INSERT", "receitas", row.get("id") if row else None, None, row)


def list_receitas(requesting_user: dict = None, ano: int = None, mes: int = None):
    sql = "SELECT * FROM receitas WHERE 1=1"
    params = []
    # aplicar filtro de ano/mes na coluna data
    conds = []
    if ano is not None:
        conds.append("strftime('%Y', data) = ?")
        params.append(f"{ano:04d}")
    if mes is not None:
        conds.append("strftime('%m', data) = ?")
        params.append(f"{mes:02d}")
    if conds:
        sql += " AND " + " AND ".join(conds)
    # visibilidade: somente registros user_id IS NULL (padrão) e do próprio usuário
    if requesting_user:
        sql += " AND (user_id IS NULL OR user_id = ?)"
        params.append(requesting_user.get("id"))
    else:
        sql += " AND user_id IS NULL"
    sql += " ORDER BY data DESC"
    return fetch_all(sql, params)


def delete_receita(receita_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM receitas WHERE id = ?", (receita_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir esta receita.")
    execute("DELETE FROM receitas WHERE id = ?", (receita_id,))
    log_action(requesting_user.get("id"), "DELETE", "receitas", receita_id, before, None)


def edit_receita(receita_id: int, data_str: str, origem: str, valor: float, observacao: str, requesting_user: dict):
    before = fetch_one("SELECT * FROM receitas WHERE id = ?", (receita_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para editar esta receita.")
    execute("UPDATE receitas SET data = ?, origem = ?, valor = ?, observacao = ? WHERE id = ?",
            (data_str, origem, valor, observacao, receita_id))
    after = fetch_one("SELECT * FROM receitas WHERE id = ?", (receita_id,))
    log_action(requesting_user.get("id"), "UPDATE", "receitas", receita_id, before, after)


# ---------------------------------------------------------------------------
# Despesas: lançamento avulso / parcelado / cartão de crédito (user-aware)
# ---------------------------------------------------------------------------

def calcular_primeira_competencia(data_compra: date, forma_pagamento: str, cartao_row=None) -> date:
    """
    Regra de negócio do cartão de crédito:
    Se a compra for feita APÓS a data de fechamento do cartão, a 1ª parcela
    cai na fatura (competência) do mês seguinte. Caso contrário, cai no mês atual.
    Para outras formas de pagamento, a competência é sempre o mês da compra.
    """
    if forma_pagamento == "Cartão de Crédito" and cartao_row is not None:
        if data_compra.day > cartao_row["dia_fechamento"]:
            return add_months(date(data_compra.year, data_compra.month, 1), 1)
        else:
            return date(data_compra.year, data_compra.month, 1)
    return date(data_compra.year, data_compra.month, 1)


def add_despesa(data_compra: date, categoria_id: int, descricao: str, valor_total: float,
                forma_pagamento: str, cartao_id: int = None, parcelas: int = 1, user_id: int = None):
    """
    Registra uma despesa (à vista ou parcelada) gerando automaticamente
    uma linha por parcela, já projetada nos meses futuros corretos.
    """
    cartao_row = None
    if cartao_id:
        cartao_row = fetch_one("SELECT * FROM cartoes WHERE id = ?", (cartao_id,))

    primeira_competencia = calcular_primeira_competencia(data_compra, forma_pagamento, cartao_row)

    parcelas = max(1, int(parcelas))
    valor_parcela = round(valor_total / parcelas, 2)
    soma_parcelas = round(valor_parcela * parcelas, 2)
    diferenca_arredondamento = round(valor_total - soma_parcelas, 2)  # ajustada na última parcela

    grupo = str(uuid.uuid4())

    for i in range(parcelas):
        competencia_i = add_months(primeira_competencia, i)
        valor_i = valor_parcela
        if i == parcelas - 1:
            valor_i = round(valor_i + diferenca_arredondamento, 2)

        execute("""
            INSERT INTO despesas
            (data_compra, data_competencia, categoria_id, descricao, valor,
             forma_pagamento, cartao_id, parcela_atual, parcela_total,
             compra_grupo, fixa, fixa_origem_id, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
        """, (
            data_compra.isoformat(), competencia_i.isoformat(), categoria_id, descricao,
            valor_i, forma_pagamento, cartao_id, i + 1, parcelas, grupo, user_id
        ))
        # log por parcela
        row = fetch_one("SELECT * FROM despesas WHERE id = (SELECT last_insert_rowid())")
        log_action(user_id, "INSERT", "despesas", row.get("id") if row else None, None, row)


def list_despesas(requesting_user: dict = None, ano: int = None, mes: int = None):
    """Lista despesas filtrando pela COMPETÊNCIA (mês em que a parcela efetivamente pesa no orçamento)."""
    sql = """
        SELECT d.*, c.nome AS categoria_nome, ca.nome AS cartao_nome
        FROM despesas d
        LEFT JOIN categorias c ON d.categoria_id = c.id
        LEFT JOIN cartoes ca ON d.cartao_id = ca.id
        WHERE 1=1
    """
    conds, params = [], []
    if ano is not None:
        conds.append("strftime('%Y', d.data_competencia) = ?")
        params.append(f"{ano:04d}")
    if mes is not None:
        conds.append("strftime('%m', d.data_competencia) = ?")
        params.append(f"{mes:02d}")
    if conds:
        sql += " AND " + " AND ".join(conds)
    # visibilidade
    if requesting_user:
        sql += " AND (d.user_id IS NULL OR d.user_id = ?)"
        params.append(requesting_user.get("id"))
    else:
        sql += " AND d.user_id IS NULL"
    sql += " ORDER BY d.data_competencia DESC, d.data_compra DESC"
    return fetch_all(sql, params)


def delete_despesa(despesa_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM despesas WHERE id = ?", (despesa_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir esta despesa.")
    execute("DELETE FROM despesas WHERE id = ?", (despesa_id,))
    log_action(requesting_user.get("id"), "DELETE", "despesas", despesa_id, before, None)


def delete_grupo(compra_grupo: str, requesting_user: dict):
    """Apaga todas as parcelas de uma mesma compra (apenas do usuário dono)."""
    rows = fetch_all("SELECT * FROM despesas WHERE compra_grupo = ?", (compra_grupo,))
    # verifica permissão para cada linha (recusa se alguma não pertencer ao solicitante)
    for r in rows:
        if not _can_access_record(requesting_user, r.get("user_id")):
            raise PermissionError("Sem permissão para excluir este grupo de compras.")
    execute("DELETE FROM despesas WHERE compra_grupo = ?", (compra_grupo,))
    # log por segurança (registro único)
    log_action(requesting_user.get("id"), "DELETE", "despesas", None, rows, None)


# ---------------------------------------------------------------------------
# Despesas fixas / recorrentes (user-aware)
# ---------------------------------------------------------------------------

def add_despesa_fixa(descricao: str, categoria_id: int, valor: float, forma_pagamento: str,
                      cartao_id: int = None, dia_vencimento: int = 1, user_id: int = None):
    execute("""
        INSERT INTO despesas_fixas
        (descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, ativa, user_id)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
    """, (descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, user_id))
    row = fetch_one("SELECT * FROM despesas_fixas WHERE id = (SELECT last_insert_rowid())")
    log_action(user_id, "INSERT", "despesas_fixas", row.get("id") if row else None, None, row)


def list_despesas_fixas(requesting_user: dict = None, somente_ativas: bool = False):
    sql = "SELECT df.*, c.nome AS categoria_nome FROM despesas_fixas df LEFT JOIN categorias c ON df.categoria_id = c.id WHERE 1=1"
    params = []
    if somente_ativas:
        sql += " AND ativa = 1"
    if requesting_user:
        sql += " AND (df.user_id IS NULL OR df.user_id = ?)"
        params.append(requesting_user.get("id"))
    else:
        sql += " AND df.user_id IS NULL"
    sql += " ORDER BY df.descricao"
    return fetch_all(sql, params)


def set_despesa_fixa_ativa(fixa_id: int, ativa: bool, requesting_user: dict):
    before = fetch_one("SELECT * FROM despesas_fixas WHERE id = ?", (fixa_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para alterar esta despesa fixa.")
    execute("UPDATE despesas_fixas SET ativa = ? WHERE id = ?", (1 if ativa else 0, fixa_id))
    after = fetch_one("SELECT * FROM despesas_fixas WHERE id = ?", (fixa_id,))
    log_action(requesting_user.get("id"), "UPDATE", "despesas_fixas", fixa_id, before, after)


def delete_despesa_fixa(fixa_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM despesas_fixas WHERE id = ?", (fixa_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir esta despesa fixa.")
    execute("DELETE FROM despesas_fixas WHERE id = ?", (fixa_id,))
    log_action(requesting_user.get("id"), "DELETE", "despesas_fixas", fixa_id, before, None)


def gerar_despesas_fixas_do_mes(ano: int, mes: int, requesting_user: dict = None):
    """
    Duplica automaticamente todas as despesas fixas ativas para o mês/ano informado,
    evitando duplicidade caso já tenham sido geradas anteriormente.
    Retorna a quantidade de lançamentos criados.
    Somente gera para despesas fixas visíveis ao requesting_user (owner ou globais).
    """
    competencia = date(ano, mes, 1).isoformat()
    criados = 0
    fixas = list_despesas_fixas(requesting_user, somente_ativas=True)
    for f in fixas:
        ja_existe = fetch_one("""
            SELECT COUNT(*) AS n FROM despesas
            WHERE fixa_origem_id = ? AND data_competencia = ?
        """, (f["id"], competencia))["n"]

        if ja_existe:
            continue

        dia = min(f.get("dia_vencimento") or 1, calendar.monthrange(ano, mes)[1])
        data_ocorrencia = date(ano, mes, dia)

        execute("""
            INSERT INTO despesas
            (data_compra, data_competencia, categoria_id, descricao, valor,
             forma_pagamento, cartao_id, parcela_atual, parcela_total,
             compra_grupo, fixa, fixa_origem_id, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, 1, ?, ?)
        """, (
            data_ocorrencia.isoformat(), competencia, f["categoria_id"], f["descricao"],
            f["valor"], f["forma_pagamento"], f["cartao_id"], str(uuid.uuid4()), f["id"], f.get("user_id")
        ))
        criados += 1
    return criados


# ---------------------------------------------------------------------------
# Configurações (reserva / aporte)
# ---------------------------------------------------------------------------

def get_reserva_percentual() -> float:
    row = fetch_one("SELECT reserva_percentual FROM config WHERE id = 1")
    return row["reserva_percentual"] if row else 0.0


def set_reserva_percentual(percentual: float):
    execute("UPDATE config SET reserva_percentual = ? WHERE id = 1", (percentual,))


# ---------------------------------------------------------------------------
# Utilitários pequenos (ex.: obter logs audit)
# ---------------------------------------------------------------------------

def get_audit_logs(limit: int = 200):
    return fetch_all("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))


# ---------------------------------------------------------------------------
# Inicialização automática (chamar init_db() ao importar em começo de app)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Inicializando/checando DB...")
    init_db()
    print("OK")
