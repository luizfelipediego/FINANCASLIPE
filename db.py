# -*- coding: utf-8 -*-
"""
db.py
Camada de acesso a dados do Sistema de Gestão Financeira Pessoal e Familiar.
Adaptado para:
- login único por usuário
- e-mail para recuperação de senha
- senhas com hash bcrypt
- área admin com reenvio de troca de senha
- isolamento total de dados por user_id
"""

import os
import sqlite3
import uuid
import calendar
import json
import traceback
import re
import secrets
from datetime import date, datetime, timedelta
from shutil import copy2

DB_PATH = "financas.db"
BACKUP_DIR = "backups"

try:
    import bcrypt
except Exception:
    bcrypt = None


def get_secret(key: str):
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key)


def usando_banco_em_nuvem() -> bool:
    return bool(get_secret("TURSO_DATABASE_URL")) and bool(get_secret("TURSO_AUTH_TOKEN"))


def get_backend_info() -> str:
    if usando_banco_em_nuvem():
        return "☁️ Turso (nuvem) — dados persistentes, não se perdem em reinícios."
    return "💻 SQLite local (financas.db) — ideal para uso/teste na sua máquina."


def nova_conexao():
    if usando_banco_em_nuvem():
        import libsql
        return libsql.connect(database=get_secret("TURSO_DATABASE_URL"), auth_token=get_secret("TURSO_AUTH_TOKEN"))
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except Exception:
        pass
    return conn


def params_para_tupla(params):
    if params is None:
        return tuple()
    if isinstance(params, tuple):
        return params
    return tuple(params)


def row_to_dict(cursor, row):
    if row is None:
        return None
    cols = [c[0] for c in cursor.description]
    return dict(zip(cols, row))


def rows_to_dicts(cursor, rows):
    if not rows:
        return []
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in rows]


def execute(sql: str, params=None):
    conn = nova_conexao()
    try:
        conn.execute(sql, params_para_tupla(params))
        conn.commit()
    finally:
        conn.close()


def fetchone(sql: str, params=None):
    conn = nova_conexao()
    try:
        cur = conn.execute(sql, params_para_tupla(params))
        return row_to_dict(cur, cur.fetchone())
    finally:
        conn.close()


def fetchall(sql: str, params=None):
    conn = nova_conexao()
    try:
        cur = conn.execute(sql, params_para_tupla(params))
        return rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_key(d: date) -> str:
    return date(d.year, d.month, 1).isoformat()


def log_action(user_id, action, table_name, row_id=None, before=None, after=None):
    execute(
        """
        INSERT INTO audit_logs (user_id, action, table_name, row_id, before_json, after_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            action,
            table_name,
            row_id,
            json.dumps(before, default=str) if before is not None else None,
            json.dumps(after, default=str) if after is not None else None,
        ),
    )


def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def backup_db():
    if usando_banco_em_nuvem():
        return None
    ensure_backup_dir()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"financas-{ts}.db")
    copy2(DB_PATH, dst)
    return dst


def send_email(to_email: str, subject: str, body: str):
    host = get_secret("SMTP_HOST")
    port = int(get_secret("SMTP_PORT") or 587)
    user = get_secret("SMTP_USER")
    passwd = get_secret("SMTP_PASS")
    if not (host and user and passwd):
        raise RuntimeError("SMTP não configurado nas secrets/variáveis de ambiente.")
    from email.message import EmailMessage
    import smtplib
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, passwd)
        s.send_message(msg)


def coluna_existe(tabela: str, coluna: str) -> bool:
    try:
        info = fetchall(f"PRAGMA table_info({tabela})")
        return any(c.get("name") == coluna for c in info)
    except Exception:
        return False


def garantir_coluna(tabela: str, coluna: str, definicao_sql: str):
    if not coluna_existe(tabela, coluna):
        try:
            execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao_sql}")
        except Exception:
            pass


CATEGORIAS_PADRAO = ["Mercado", "Saúde/Remédios", "Estudos/Educação", "Lazer", "Moradia", "Veículo", "Outros"]


def init_db():
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
            banco TEXT DEFAULT NULL,
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
            user_id INTEGER DEFAULT NULL
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
            user_id INTEGER DEFAULT NULL
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY,
            reserva_percentual REAL DEFAULT 10
        )
    """)
    execute("INSERT OR IGNORE INTO config (id, reserva_percentual) VALUES (1, 10)")
    execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            reset_token TEXT,
            reset_expires_at TEXT
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            table_name TEXT NOT NULL,
            row_id INTEGER,
            before_json TEXT,
            after_json TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ensure_backup_dir()
    _migrar_estrutura_antiga()
    _migrar_logins_existentes()


def _migrar_estrutura_antiga():
    garantir_coluna("categorias", "teto_mensal", "REAL DEFAULT 0")
    garantir_coluna("categorias", "user_id", "INTEGER DEFAULT NULL")
    garantir_coluna("cartoes", "dia_fechamento", "INTEGER")
    garantir_coluna("cartoes", "dia_vencimento", "INTEGER")
    garantir_coluna("cartoes", "banco", "TEXT DEFAULT NULL")
    garantir_coluna("cartoes", "user_id", "INTEGER DEFAULT NULL")
    garantir_coluna("receitas", "user_id", "INTEGER DEFAULT NULL")
    garantir_coluna("despesas_fixas", "categoria_id", "INTEGER")
    garantir_coluna("despesas_fixas", "forma_pagamento", "TEXT")
    garantir_coluna("despesas_fixas", "cartao_id", "INTEGER")
    garantir_coluna("despesas_fixas", "dia_vencimento", "INTEGER DEFAULT 1")
    garantir_coluna("despesas_fixas", "ativa", "INTEGER DEFAULT 1")
    garantir_coluna("despesas_fixas", "user_id", "INTEGER DEFAULT NULL")
    garantir_coluna("despesas", "data_competencia", "TEXT")
    garantir_coluna("despesas", "categoria_id", "INTEGER")
    garantir_coluna("despesas", "forma_pagamento", "TEXT")
    garantir_coluna("despesas", "cartao_id", "INTEGER")
    garantir_coluna("despesas", "parcela_atual", "INTEGER DEFAULT 1")
    garantir_coluna("despesas", "parcela_total", "INTEGER DEFAULT 1")
    garantir_coluna("despesas", "compra_grupo", "TEXT")
    garantir_coluna("despesas", "fixa", "INTEGER DEFAULT 0")
    garantir_coluna("despesas", "fixa_origem_id", "INTEGER")
    garantir_coluna("despesas", "user_id", "INTEGER DEFAULT NULL")
    garantir_coluna("users", "login", "TEXT")
    garantir_coluna("users", "password_hash", "TEXT")
    garantir_coluna("users", "is_admin", "INTEGER DEFAULT 0")
    garantir_coluna("users", "created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")
    garantir_coluna("users", "reset_token", "TEXT")
    garantir_coluna("users", "reset_expires_at", "TEXT")


def normalize_login(login: str) -> str:
    login = (login or "").strip().lower()
    return re.sub(r"[^a-z0-9._-]", "", login)


def validate_password(password: str):
    if password is None:
        return False, "Informe uma senha."
    if len(password) < 4:
        return False, "A senha deve ter pelo menos 4 caracteres."
    if len(password) > 10:
        return False, "A senha deve ter no máximo 10 caracteres."
    if not password.isalnum():
        return False, "A senha deve conter apenas letras e números."
    return True, "OK"


def _base_login_from_email(email: str) -> str:
    base = (email or "usuario").split("@")[0]
    base = normalize_login(base)
    return base or "usuario"


def _login_existe(login: str, exclude_user_id=None) -> bool:
    if exclude_user_id is None:
        row = fetchone("SELECT id FROM users WHERE login = ?", (login,))
    else:
        row = fetchone("SELECT id FROM users WHERE login = ? AND id <> ?", (login, exclude_user_id))
    return row is not None


def _gerar_login_unico(base: str, exclude_user_id=None) -> str:
    base = normalize_login(base) or "usuario"
    candidato = base
    sufixo = 1
    while _login_existe(candidato, exclude_user_id):
        sufixo += 1
        candidato = f"{base}{sufixo}"
    return candidato


def _migrar_logins_existentes():
    try:
        users = fetchall("SELECT id, email, login FROM users ORDER BY id")
        for u in users:
            login = normalize_login(u.get("login") or "")
            if not login:
                login = _base_login_from_email(u.get("email"))
            login = _gerar_login_unico(login, exclude_user_id=u.get("id"))
            execute("UPDATE users SET login = ? WHERE id = ?", (login, u.get("id")))
        execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_login_unique ON users(login)")
    except Exception:
        pass


def seed_categorias_padrao(user_id: int):
    total = fetchone("SELECT COUNT(*) AS n FROM categorias WHERE user_id = ?", (user_id,))
    if total and total.get("n", 0) > 0:
        return
    for nome in CATEGORIAS_PADRAO:
        execute("INSERT INTO categorias (nome, teto_mensal, user_id) VALUES (?, 0, ?)", (nome, user_id))


def hash_password(password: str) -> str:
    if bcrypt is None:
        raise RuntimeError("bcrypt não instalado. Rode: pip install bcrypt")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    if bcrypt is None:
        raise RuntimeError("bcrypt não instalado. Rode: pip install bcrypt")
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_user(login: str, email: str, password: str, is_admin: bool = False):
    login = normalize_login(login)
    email = (email or "").strip().lower()
    if not login:
        raise ValueError("Informe um login válido.")
    if _login_existe(login):
        raise ValueError("Esse login já existe. Escolha outro.")
    if not email or "@" not in email:
        raise ValueError("Informe um e-mail válido.")
    if fetchone("SELECT id FROM users WHERE email = ?", (email,)):
        raise ValueError("Esse e-mail já está cadastrado.")
    ok, msg = validate_password(password)
    if not ok:
        raise ValueError(msg)
    senha_hash = hash_password(password)
    execute(
        "INSERT INTO users (login, email, password_hash, is_admin) VALUES (?, ?, ?, ?)",
        (login, email, senha_hash, 1 if is_admin else 0),
    )
    row = fetchone("SELECT id FROM users WHERE login = ?", (login,))
    novo_id = row["id"] if row else None
    if novo_id:
        seed_categorias_padrao(novo_id)
    return novo_id


def get_user_by_login(login: str):
    return fetchone("SELECT * FROM users WHERE login = ?", (normalize_login(login),))


def get_user_by_email(email: str):
    return fetchone("SELECT * FROM users WHERE email = ?", ((email or "").strip().lower(),))


def get_user_by_id(user_id: int):
    return fetchone("SELECT * FROM users WHERE id = ?", (user_id,))


def authenticate_user(login_or_email: str, password: str):
    u = get_user_by_login(login_or_email)
    if u is None and "@" in (login_or_email or ""):
        u = get_user_by_email(login_or_email)
    if not u:
        return None
    if verify_password(password, u["password_hash"]):
        return {k: v for k, v in u.items() if k != "password_hash"}
    return None


def set_user_password(user_id: int, new_password: str):
    ok, msg = validate_password(new_password)
    if not ok:
        raise ValueError(msg)
    execute(
        "UPDATE users SET password_hash = ?, reset_token = NULL, reset_expires_at = NULL WHERE id = ?",
        (hash_password(new_password), user_id),
    )


def create_password_reset_token(user_id: int, hours_valid: int = 1):
    token = secrets.token_urlsafe(32)
    expira = (datetime.now() + timedelta(hours=hours_valid)).isoformat(timespec="seconds")
    execute("UPDATE users SET reset_token = ?, reset_expires_at = ? WHERE id = ?", (token, expira, user_id))
    return token


def get_user_by_reset_token(token: str):
    row = fetchone("SELECT * FROM users WHERE reset_token = ?", (token,))
    if not row:
        return None
    expira = row.get("reset_expires_at")
    if not expira:
        return None
    try:
        if datetime.now() > datetime.fromisoformat(expira):
            return None
    except Exception:
        return None
    return row


def send_password_reset_email(user_id: int, base_url: str, requested_by: str = "usuário"):
    user = get_user_by_id(user_id)
    if not user:
        return False
    token = create_password_reset_token(user_id)
    link = f"{base_url.rstrip('/')}/?reset_token={token}"
    body = (
        f"Olá, {user.get('login')}!\n\n"
        f"Foi solicitada uma redefinição de senha por {requested_by}.\n"
        f"Acesse o link abaixo para criar uma nova senha:\n{link}\n\n"
        f"Esse link expira em 1 hora."
    )
    send_email(user.get("email"), "Redefinição de senha", body)
    return True


def request_password_reset_by_email(email: str, base_url: str):
    user = get_user_by_email(email)
    if not user:
        return False
    return send_password_reset_email(user["id"], base_url, requested_by="recuperação de acesso")


def reset_password_with_token(token: str, new_password: str):
    user = get_user_by_reset_token(token)
    if not user:
        return False, "Token inválido ou expirado."
    ok, msg = validate_password(new_password)
    if not ok:
        return False, msg
    set_user_password(user["id"], new_password)
    log_action(user["id"], "PASSWORD_RESET", "users", user["id"], None, {"login": user.get("login")})
    return True, "Senha redefinida com sucesso."


def can_access_record(requesting_user, record_user_id) -> bool:
    if requesting_user is None:
        return False
    return requesting_user.get("id") == record_user_id


def add_categoria(nome: str, teto_mensal: float = 0.0, user_id: int = None):
    execute("INSERT INTO categorias (nome, teto_mensal, user_id) VALUES (?, ?, ?)", (nome.strip(), teto_mensal, user_id))


def list_categorias(requesting_user=None):
    if not requesting_user:
        return []
    return fetchall("SELECT * FROM categorias WHERE user_id = ? ORDER BY nome", (requesting_user.get("id"),))


def update_categoria_teto(categoria_id: int, teto_mensal: float, requesting_user):
    before = fetchone("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    if not before or not can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para alterar esta categoria.")
    execute("UPDATE categorias SET teto_mensal = ? WHERE id = ?", (teto_mensal, categoria_id))
    after = fetchone("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    log_action(requesting_user.get("id"), "UPDATE", "categorias", categoria_id, before, after)


def delete_categoria(categoria_id: int, requesting_user):
    before = fetchone("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    if not before or not can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir esta categoria.")
    execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
    log_action(requesting_user.get("id"), "DELETE", "categorias", categoria_id, before, None)


def add_cartao(nome: str, dia_fechamento: int, dia_vencimento: int, banco: str = None, user_id: int = None):
    execute(
        "INSERT INTO cartoes (nome, dia_fechamento, dia_vencimento, banco, user_id) VALUES (?, ?, ?, ?, ?)",
        (nome.strip(), dia_fechamento, dia_vencimento, banco, user_id),
    )


def list_cartoes(requesting_user=None):
    if not requesting_user:
        return []
    return fetchall("SELECT * FROM cartoes WHERE user_id = ? ORDER BY nome", (requesting_user.get("id"),))


def delete_cartao(cartao_id: int, requesting_user):
    before = fetchone("SELECT * FROM cartoes WHERE id = ?", (cartao_id,))
    if not before or not can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir este cartão.")
    execute("DELETE FROM cartoes WHERE id = ?", (cartao_id,))
    log_action(requesting_user.get("id"), "DELETE", "cartoes", cartao_id, before, None)


def add_receita(data_str: str, origem: str, valor: float, observacao: str = "", user_id: int = None):
    execute("INSERT INTO receitas (data, origem, valor, observacao, user_id) VALUES (?, ?, ?, ?, ?)", (data_str, origem, valor, observacao, user_id))
    row = fetchone("SELECT * FROM receitas WHERE id = (SELECT last_insert_rowid())")
    log_action(user_id, "INSERT", "receitas", row.get("id") if row else None, None, row)


def list_receitas(requesting_user=None, ano: int = None, mes: int = None):
    if not requesting_user:
        return []
    sql = "SELECT * FROM receitas WHERE user_id = ?"
    params = [requesting_user.get("id")]
    if ano is not None:
        sql += " AND strftime('%Y', data) = ?"
        params.append(f"{ano:04d}")
    if mes is not None:
        sql += " AND strftime('%m', data) = ?"
        params.append(f"{mes:02d}")
    sql += " ORDER BY data DESC"
    return fetchall(sql, params)


def delete_receita(receita_id: int, requesting_user):
    before = fetchone("SELECT * FROM receitas WHERE id = ?", (receita_id,))
    if not before or not can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir esta receita.")
    execute("DELETE FROM receitas WHERE id = ?", (receita_id,))
    log_action(requesting_user.get("id"), "DELETE", "receitas", receita_id, before, None)


def calcular_primeira_competencia(data_compra: date, forma_pagamento: str, cartao_row=None) -> date:
    if forma_pagamento == "Cartão de Crédito" and cartao_row is not None:
        if data_compra.day > cartao_row["dia_fechamento"]:
            return add_months(date(data_compra.year, data_compra.month, 1), 1)
    return date(data_compra.year, data_compra.month, 1)


def add_despesa(data_compra: date, categoria_id: int, descricao: str, valor_total: float,
                forma_pagamento: str, cartao_id: int = None, parcelas: int = 1, user_id: int = None):
    cartao_row = fetchone("SELECT * FROM cartoes WHERE id = ?", (cartao_id,)) if cartao_id else None
    primeira_comp = calcular_primeira_competencia(data_compra, forma_pagamento, cartao_row)
    parcelas = max(1, int(parcelas))
    valor_parcela = round(valor_total / parcelas, 2)
    soma = round(valor_parcela * parcelas, 2)
    diferenca = round(valor_total - soma, 2)
    grupo = str(uuid.uuid4())
    for i in range(parcelas):
        comp_i = add_months(primeira_comp, i)
        valor_i = valor_parcela if i < parcelas - 1 else round(valor_parcela + diferenca, 2)
        execute(
            """
            INSERT INTO despesas (
                data_compra, data_competencia, categoria_id, descricao, valor,
                forma_pagamento, cartao_id, parcela_atual, parcela_total, compra_grupo,
                fixa, fixa_origem_id, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
            """,
            (
                data_compra.isoformat(), comp_i.isoformat(), categoria_id, descricao, valor_i,
                forma_pagamento, cartao_id, i + 1, parcelas, grupo, user_id,
            ),
        )


def list_despesas(requesting_user=None, ano: int = None, mes: int = None):
    if not requesting_user:
        return []
    sql = """
    SELECT d.*, c.nome AS categoria_nome, ca.nome AS cartao_nome
    FROM despesas d
    LEFT JOIN categorias c ON d.categoria_id = c.id
    LEFT JOIN cartoes ca ON d.cartao_id = ca.id
    WHERE d.user_id = ?
    """
    params = [requesting_user.get("id")]
    if ano is not None:
        sql += " AND strftime('%Y', d.data_competencia) = ?"
        params.append(f"{ano:04d}")
    if mes is not None:
        sql += " AND strftime('%m', d.data_competencia) = ?"
        params.append(f"{mes:02d}")
    sql += " ORDER BY d.data_competencia DESC, d.data_compra DESC"
    return fetchall(sql, params)


def delete_despesa(despesa_id: int, requesting_user):
    before = fetchone("SELECT * FROM despesas WHERE id = ?", (despesa_id,))
    if not before or not can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir esta despesa.")
    execute("DELETE FROM despesas WHERE id = ?", (despesa_id,))
    log_action(requesting_user.get("id"), "DELETE", "despesas", despesa_id, before, None)


def delete_grupo(compra_grupo: str, requesting_user):
    rows = fetchall("SELECT * FROM despesas WHERE compra_grupo = ?", (compra_grupo,))
    for r in rows:
        if not can_access_record(requesting_user, r.get("user_id")):
            raise PermissionError("Sem permissão para excluir este grupo de compras.")
    execute("DELETE FROM despesas WHERE compra_grupo = ?", (compra_grupo,))
    log_action(requesting_user.get("id"), "DELETE", "despesas", None, rows, None)


def add_despesa_fixa(descricao: str, categoria_id: int, valor: float, forma_pagamento: str,
                     cartao_id: int = None, dia_vencimento: int = 1, user_id: int = None):
    execute(
        """
        INSERT INTO despesas_fixas (descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, ativa, user_id)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, user_id),
    )


def list_despesas_fixas(requesting_user=None, somente_ativas: bool = False):
    if not requesting_user:
        return []
    sql = """
    SELECT df.*, c.nome AS categoria_nome
    FROM despesas_fixas df
    LEFT JOIN categorias c ON df.categoria_id = c.id
    WHERE df.user_id = ?
    """
    params = [requesting_user.get("id")]
    if somente_ativas:
        sql += " AND ativa = 1"
    sql += " ORDER BY df.descricao"
    return fetchall(sql, params)


def set_despesa_fixa_ativa(fixa_id: int, ativa: bool, requesting_user):
    before = fetchone("SELECT * FROM despesas_fixas WHERE id = ?", (fixa_id,))
    if not before or not can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para alterar esta despesa fixa.")
    execute("UPDATE despesas_fixas SET ativa = ? WHERE id = ?", (1 if ativa else 0, fixa_id))
    after = fetchone("SELECT * FROM despesas_fixas WHERE id = ?", (fixa_id,))
    log_action(requesting_user.get("id"), "UPDATE", "despesas_fixas", fixa_id, before, after)


def delete_despesa_fixa(fixa_id: int, requesting_user):
    before = fetchone("SELECT * FROM despesas_fixas WHERE id = ?", (fixa_id,))
    if not before or not can_access_record(requesting_user, before.get("user_id")):
        raise PermissionError("Sem permissão para excluir esta despesa fixa.")
    execute("DELETE FROM despesas_fixas WHERE id = ?", (fixa_id,))
    log_action(requesting_user.get("id"), "DELETE", "despesas_fixas", fixa_id, before, None)


def gerar_despesas_fixas_do_mes(ano: int, mes: int, requesting_user=None):
    if not requesting_user:
        return 0
    competencia = date(ano, mes, 1).isoformat()
    criados = 0
    fixas = list_despesas_fixas(requesting_user, somente_ativas=True)
    for f in fixas:
        ja = fetchone(
            "SELECT COUNT(*) AS n FROM despesas WHERE fixa_origem_id = ? AND data_competencia = ?",
            (f["id"], competencia),
        )
        if ja and ja.get("n", 0) > 0:
            continue
        dia = min(f.get("dia_vencimento") or 1, calendar.monthrange(ano, mes)[1])
        data_ocorrencia = date(ano, mes, dia)
        execute(
            """
            INSERT INTO despesas (
                data_compra, data_competencia, categoria_id, descricao, valor,
                forma_pagamento, cartao_id, parcela_atual, parcela_total, compra_grupo,
                fixa, fixa_origem_id, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, 1, ?, ?)
            """,
            (
                data_ocorrencia.isoformat(), competencia, f["categoria_id"], f["descricao"], f["valor"],
                f["forma_pagamento"], f["cartao_id"], str(uuid.uuid4()), f["id"], f["user_id"],
            ),
        )
        criados += 1
    return criados


def get_reserva_percentual() -> float:
    row = fetchone("SELECT reserva_percentual FROM config WHERE id = 1")
    return row["reserva_percentual"] if row else 0.0


def set_reserva_percentual(percentual: float):
    execute("UPDATE config SET reserva_percentual = ? WHERE id = 1", (percentual,))


def get_audit_logs(limit: int = 200):
    return fetchall("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))


# -------------------------------------------------
# Camada de compatibilidade com o app antigo
# -------------------------------------------------
def create_user_compat(email: str, password: str, is_admin: bool = False):
    login = _gerar_login_unico(_base_login_from_email(email))
    return create_user(login, email, password, is_admin=is_admin)


def create_initial_admin(login: str, email: str, password: str, send_email_flag: bool = False):
    admin_id = create_user(login, email, password, is_admin=True)
    if send_email_flag:
        try:
            send_email(email, "Acesso de administrador", f"Seu login é {login}.")
        except Exception:
            pass
    return admin_id


# aliases do código antigo
get_backend_info_old = get_backend_info
backup_db_old = backup_db

# aliases usados pelo app existente
create_user_from_email = create_user_compat
get_user_by_email_old = get_user_by_email
set_user_password_old = set_user_password

# aliases exatos compatíveis com app enviado
get_backend_info_alias = get_backend_info

# nomes antigos do projeto
get_backend_info = get_backend_info
backup_db = backup_db
create_user_old = create_user_compat
get_user_by_email = get_user_by_email
get_user_by_id = get_user_by_id
authenticate_user = authenticate_user
set_user_password = set_user_password
add_categoria_old = add_categoria
list_categorias_old = list_categorias
update_categoria_teto_old = update_categoria_teto
delete_categoria_old = delete_categoria
add_cartao_old = add_cartao
list_cartoes_old = list_cartoes
delete_cartao_old = delete_cartao
add_receita_old = add_receita
list_receitas_old = list_receitas
delete_receita_old = delete_receita
add_despesa_old = add_despesa
list_despesas_old = list_despesas
delete_despesa_old = delete_despesa
delete_grupo_old = delete_grupo
add_despesa_fixa_old = add_despesa_fixa
list_despesas_fixas_old = list_despesas_fixas
set_despesa_fixa_ativa_old = set_despesa_fixa_ativa
delete_despesa_fixa_old = delete_despesa_fixa
gerar_despesas_fixas_do_mes_old = gerar_despesas_fixas_do_mes
get_reserva_percentual_old = get_reserva_percentual
set_reserva_percentual_old = set_reserva_percentual
get_audit_logs_old = get_audit_logs

# aliases snake_case -> nomes do app enviado
create_user_email = create_user_compat

# nomes do app-2.py
create_user = create_user
authenticate_user = authenticate_user
set_user_password = set_user_password
list_receitas = list_receitas
list_despesas = list_despesas
list_despesas_fixas = list_despesas_fixas
list_categorias = list_categorias
list_cartoes = list_cartoes
add_receita = add_receita
add_despesa = add_despesa
add_despesa_fixa = add_despesa_fixa
add_categoria = add_categoria
add_cartao = add_cartao
delete_receita = delete_receita
delete_despesa = delete_despesa
delete_grupo = delete_grupo
delete_despesa_fixa = delete_despesa_fixa
delete_categoria = delete_categoria
delete_cartao = delete_cartao
update_categoria_teto = update_categoria_teto
set_despesa_fixa_ativa = set_despesa_fixa_ativa
gerar_despesas_fixas_do_mes = gerar_despesas_fixas_do_mes
calcular_primeira_competencia = calcular_primeira_competencia
add_months = add_months

# nomes em camel/snake do arquivo original para compatibilidade direta
usando_banco_em_nuvem = usando_banco_em_nuvem
get_backend_info = get_backend_info
fetchall = fetchall
fetchone = fetchone
init_db = init_db
backup_db = backup_db
send_email = send_email
validate_password = validate_password
request_password_reset_by_email = request_password_reset_by_email
send_password_reset_email = send_password_reset_email
reset_password_with_token = reset_password_with_token

if __name__ == "__main__":
    print("Inicializando/checando DB...")
    init_db()
    print("OK")
