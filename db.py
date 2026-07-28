# -*- coding: utf-8 -*-
"""
db.py
=====
Camada de acesso a dados do Sistema de Gestão Financeira Pessoal e Familiar.
"""

import os
import sys
import sqlite3
import uuid
import secrets
import calendar
import json
import traceback
from datetime import date, datetime, timedelta, timezone
from shutil import copy2

DB_PATH = "financas.db"
BACKUP_DIR = "backups"

try:
    import bcrypt
except Exception:
    bcrypt = None

def _get_secret(key: str):
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key)

def usando_banco_em_nuvem() -> bool:
    return bool(_get_secret("TURSO_DATABASE_URL")) and bool(_get_secret("TURSO_AUTH_TOKEN"))

def get_backend_info() -> str:
    if usando_banco_em_nuvem():
        return "☁️ Turso (nuvem) — dados persistentes, não se perdem em reinícios"
    return "💻 SQLite local (financas.db) — ideal para uso/teste na sua máquina"

def _nova_conexao():
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
    msg = str(exc).lower()
    return "stream not found" in msg or "stream_not_found" in msg or ("hrana" in msg and "404" in msg)

def _params_para_tupla(params):
    if params is None:
        return ()
    if isinstance(params, tuple):
        return params
    return tuple(params)

def _log_erro_diagnostico(sql, params, tentativa_formato, exc):
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
    params = _params_para_tupla(params)
    tentativas = [("tupla", params), ("lista", list(params))]
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

def execute(sql: str, params=()):
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

def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

def month_key(d: date) -> str:
    return date(d.year, d.month, 1).isoformat()

def log_action(user_id, action, table_name, row_id=None, before=None, after=None):
    execute("""
        INSERT INTO audit_logs
        (user_id, action, table_name, row_id, before_json, after_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id, action, table_name, row_id,
        json.dumps(before, default=str) if before is not None else None,
        json.dumps(after, default=str) if after is not None else None
    ))

def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def backup_db():
    if usando_banco_em_nuvem():
        return None
    ensure_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    src = DB_PATH
    dst = os.path.join(BACKUP_DIR, f"financas-{timestamp}.db")
    copy2(src, dst)
    return dst

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

def _coluna_existe(tabela: str, coluna: str) -> bool:
    try:
        info = fetch_all(f"PRAGMA table_info({tabela})")
        return any(c.get("name") == coluna for c in info)
    except Exception:
        return False

def _garantir_coluna(tabela: str, coluna: str, definicao_sql: str):
    if not _coluna_existe(tabela, coluna):
        try: execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao_sql}")
        except Exception: pass

def _corrigir_chaves_estrangeiras_residuais():
    try:
        tabelas = fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND (sql LIKE '%_migracao_old%' OR sql LIKE '%__nova_sem_unique%')")
        nomes = [t["name"] for t in tabelas]

        if "despesas_fixas" not in nomes and "despesas" not in nomes: return 
        try: execute("DROP TABLE IF EXISTS despesas_bkp")
        except: pass
        try: execute("DROP TABLE IF EXISTS despesas_fixas_bkp")
        except: pass

        if "despesas" in nomes: execute("ALTER TABLE despesas RENAME TO despesas_bkp")
        if "despesas_fixas" in nomes: execute("ALTER TABLE despesas_fixas RENAME TO despesas_fixas_bkp")

        if "despesas_fixas" in nomes:
            execute("""
            CREATE TABLE despesas_fixas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, descricao TEXT NOT NULL, categoria_id INTEGER,
                valor REAL NOT NULL, forma_pagamento TEXT NOT NULL, cartao_id INTEGER,
                dia_vencimento INTEGER DEFAULT 1, ativa INTEGER DEFAULT 1, user_id INTEGER DEFAULT NULL,
                FOREIGN KEY (categoria_id) REFERENCES categorias(id), FOREIGN KEY (cartao_id) REFERENCES cartoes(id)
            )""")
            execute("""
            INSERT INTO despesas_fixas (id, descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, ativa, user_id)
            SELECT id, descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, ativa, user_id FROM despesas_fixas_bkp
            """)

        if "despesas" in nomes:
            execute("""
            CREATE TABLE despesas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, data_compra TEXT NOT NULL, data_competencia TEXT NOT NULL,
                categoria_id INTEGER, descricao TEXT NOT NULL, valor REAL NOT NULL, forma_pagamento TEXT NOT NULL,
                cartao_id INTEGER, parcela_atual INTEGER DEFAULT 1, parcela_total INTEGER DEFAULT 1,
                compra_grupo TEXT, fixa INTEGER DEFAULT 0, fixa_origem_id INTEGER, user_id INTEGER DEFAULT NULL,
                FOREIGN KEY (categoria_id) REFERENCES categorias(id), FOREIGN KEY (cartao_id) REFERENCES cartoes(id),
                FOREIGN KEY (fixa_origem_id) REFERENCES despesas_fixas(id)
            )""")
            execute("""
            INSERT INTO despesas (id, data_compra, data_competencia, categoria_id, descricao, valor, forma_pagamento, cartao_id, parcela_atual, parcela_total, compra_grupo, fixa, fixa_origem_id, user_id)
            SELECT id, data_compra, data_competencia, categoria_id, descricao, valor, forma_pagamento, cartao_id, parcela_atual, parcela_total, compra_grupo, fixa, fixa_origem_id, user_id FROM despesas_bkp
            """)

        if "despesas" in nomes:
            try: execute("DROP TABLE despesas_bkp")
            except: pass
        if "despesas_fixas" in nomes:
            try: execute("DROP TABLE despesas_fixas_bkp")
            except: pass

    except Exception as e:
        print(f"[MIGRAÇÃO] Falha ao recriar tabelas (FK): {e}", file=sys.stderr)

def init_db():
    execute("""
    CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, teto_mensal REAL DEFAULT 0, user_id INTEGER DEFAULT NULL)
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS cartoes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, dia_fechamento INTEGER NOT NULL, dia_vencimento INTEGER NOT NULL, user_id INTEGER DEFAULT NULL)
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS receitas (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, origem TEXT NOT NULL, valor REAL NOT NULL, observacao TEXT, user_id INTEGER DEFAULT NULL)
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS despesas_fixas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, descricao TEXT NOT NULL, categoria_id INTEGER, valor REAL NOT NULL, forma_pagamento TEXT NOT NULL, cartao_id INTEGER, dia_vencimento INTEGER DEFAULT 1, ativa INTEGER DEFAULT 1, user_id INTEGER DEFAULT NULL,
        FOREIGN KEY (categoria_id) REFERENCES categorias(id), FOREIGN KEY (cartao_id) REFERENCES cartoes(id)
    )
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS despesas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, data_compra TEXT NOT NULL, data_competencia TEXT NOT NULL, categoria_id INTEGER, descricao TEXT NOT NULL, valor REAL NOT NULL, forma_pagamento TEXT NOT NULL, cartao_id INTEGER, parcela_atual INTEGER DEFAULT 1, parcela_total INTEGER DEFAULT 1, compra_grupo TEXT, fixa INTEGER DEFAULT 0, fixa_origem_id INTEGER, user_id INTEGER DEFAULT NULL,
        FOREIGN KEY (categoria_id) REFERENCES categorias(id), FOREIGN KEY (cartao_id) REFERENCES cartoes(id), FOREIGN KEY (fixa_origem_id) REFERENCES despesas_fixas(id)
    )
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, reserva_percentual REAL DEFAULT 10)
    """)
    execute("INSERT OR IGNORE INTO config (id, reserva_percentual) VALUES (1, 10)")
    execute("""
    CREATE TABLE IF NOT EXISTS migracoes_executadas (nome TEXT PRIMARY KEY, executado_em TEXT DEFAULT (datetime('now')))
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, is_admin INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')))
    """)
    execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT NOT NULL, table_name TEXT NOT NULL, row_id INTEGER, before_json TEXT, after_json TEXT, timestamp TEXT DEFAULT (datetime('now')))
    """)

    _garantir_coluna("categorias", "user_id", "INTEGER DEFAULT NULL")
    _garantir_coluna("cartoes", "user_id", "INTEGER DEFAULT NULL")
    _garantir_coluna("cartoes", "banco", "TEXT DEFAULT NULL")
    _garantir_coluna("receitas", "user_id", "INTEGER DEFAULT NULL")
    _garantir_coluna("despesas_fixas", "user_id", "INTEGER DEFAULT NULL")
    _garantir_coluna("despesas_fixas", "dia_vencimento", "INTEGER DEFAULT 1")
    _garantir_coluna("despesas_fixas", "ativa", "INTEGER DEFAULT 1")
    _garantir_coluna("despesas", "user_id", "INTEGER DEFAULT NULL")
    _garantir_coluna("despesas", "data_competencia", "TEXT")
    _garantir_coluna("despesas", "parcela_atual", "INTEGER DEFAULT 1")
    _garantir_coluna("despesas", "parcela_total", "INTEGER DEFAULT 1")
    _garantir_coluna("despesas", "compra_grupo", "TEXT")
    _garantir_coluna("despesas", "fixa", "INTEGER DEFAULT 0")
    _garantir_coluna("despesas", "fixa_origem_id", "INTEGER")
    _garantir_coluna("users", "reset_token", "TEXT DEFAULT NULL")
    _garantir_coluna("users", "reset_token_expires_at", "TEXT DEFAULT NULL")

    try:
        execute("""
            UPDATE despesas SET data_competencia = data_compra
            WHERE data_competencia IS NULL OR data_competencia = ''
        """)
    except Exception:
        pass

    _corrigir_chaves_estrangeiras_residuais()
    _executar_migracao_uma_vez("remover_unique_categorias", _migrar_categorias_remover_unique_global)
    _executar_migracao_uma_vez("remover_unique_cartoes", _migrar_cartoes_remover_unique_global)
    _executar_migracao_uma_vez("remover_unique_despesas_fixas", _migrar_despesas_fixas_remover_unique_global)

    try:
        usuarios_sem_categoria = fetch_all("""
            SELECT u.id AS id FROM users u LEFT JOIN categorias c ON c.user_id = u.id GROUP BY u.id HAVING COUNT(c.id) = 0
        """)
        for u in usuarios_sem_categoria:
            seed_categorias_padrao(u["id"])
    except Exception:
        pass

    ensure_backup_dir()

def _tabela_tem_unique_em_coluna(tabela: str, coluna: str) -> bool:
    try:
        row = fetch_one("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tabela,))
        sql_tabela = (row.get("sql") or "") if row else ""
        if "UNIQUE" in sql_tabela.upper(): return True
    except Exception: pass
    try:
        indices = fetch_all(f"PRAGMA index_list({tabela})")
        for idx in indices:
            if idx.get("unique"):
                info = fetch_all(f"PRAGMA index_info({idx.get('name')})")
                if any(c.get("name") == coluna for c in info): return True
    except Exception: pass
    return False

def _tabela_existe(nome: str) -> bool:
    try:
        row = fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (nome,))
        return row is not None
    except Exception:
        return False

def _executar_migracao_uma_vez(nome: str, funcao):
    try: ja_feita = fetch_one("SELECT 1 FROM migracoes_executadas WHERE nome = ?", (nome,))
    except Exception: ja_feita = None
    if ja_feita: return
    try:
        funcao()
        execute("INSERT OR IGNORE INTO migracoes_executadas (nome) VALUES (?)", (nome,))
    except Exception as e:
        print(f"[MIGRAÇÃO] '{nome}' não concluída, será tentada novamente depois: {type(e).__name__}: {e}", file=sys.stderr)

def _reconciliar_residuos_de_tentativas_antigas(tabela: str, colunas: list):
    colunas_sem_id = [c for c in colunas if c != "id"]
    colunas_str = ", ".join(colunas_sem_id)
    for nome_residuo in (f"{tabela}_migracao_old", f"{tabela}__nova_sem_unique"):
        if not _tabela_existe(nome_residuo): continue
        try: execute(f"INSERT INTO {tabela} ({colunas_str}) SELECT {colunas_str} FROM {nome_residuo}")
        except Exception as e: pass
        try: execute(f"DROP TABLE IF EXISTS {nome_residuo}")
        except Exception as e: pass

def _remover_unique_sem_recriar_tabela(tabela: str, coluna: str) -> bool:
    if not _tabela_tem_unique_em_coluna(tabela, coluna): return True
    conn = _nova_conexao()
    try:
        conn.execute("PRAGMA writable_schema = ON")
        conn.execute("UPDATE sqlite_master SET sql = REPLACE(sql, 'UNIQUE', '') WHERE type = 'table' AND name = ? AND sql LIKE '%UNIQUE%'", (tabela,))
        conn.execute("DELETE FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND name LIKE 'sqlite_autoindex_%'", (tabela,))
        conn.execute("PRAGMA writable_schema = OFF")
        conn.commit()
    except Exception as e:
        try: conn.execute("PRAGMA writable_schema = OFF")
        except Exception: pass
        try: conn.rollback()
        except Exception: pass
        return False
    finally:
        conn.close()
    return not _tabela_tem_unique_em_coluna(tabela, coluna)

def _migrar_categorias_remover_unique_global(reconciliar_residuos: bool = False):
    if reconciliar_residuos: _reconciliar_residuos_de_tentativas_antigas("categorias", ["id", "nome", "teto_mensal", "user_id"])
    _remover_unique_sem_recriar_tabela("categorias", "nome")

def _migrar_cartoes_remover_unique_global(reconciliar_residuos: bool = False):
    if reconciliar_residuos: _reconciliar_residuos_de_tentativas_antigas("cartoes", ["id", "nome", "dia_fechamento", "dia_vencimento", "user_id", "banco"])
    _remover_unique_sem_recriar_tabela("cartoes", "nome")

def _migrar_despesas_fixas_remover_unique_global(reconciliar_residuos: bool = False):
    if reconciliar_residuos: _reconciliar_residuos_de_tentativas_antigas("despesas_fixas", ["id", "descricao", "categoria_id", "valor", "forma_pagamento", "cartao_id", "dia_vencimento", "ativa", "user_id"])
    _remover_unique_sem_recriar_tabela("despesas_fixas", "descricao")

CATEGORIAS_PADRAO = ["Mercado", "Saúde/Remédios", "Lazer e Jogos", "Moradia", "Veículo", "Investimentos (FIIs e Renda Fixa)", "Paiva Projetos e Consultoria", "Filho", "Outros"]

def seed_categorias_padrao(user_id: int):
    total = fetch_one("SELECT COUNT(*) AS n FROM categorias WHERE user_id = ?", (user_id,))
    if total and total["n"] > 0: return
    for nome in CATEGORIAS_PADRAO:
        execute("INSERT INTO categorias (nome, teto_mensal, user_id) VALUES (?, 0, ?)", (nome, user_id))

def _hash_password(password: str) -> str:
    if bcrypt is None: raise RuntimeError("bcrypt não instalado.")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(password: str, hashed: str) -> bool:
    if bcrypt is None: raise RuntimeError("bcrypt não instalado.")
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def create_user(email: str, password: str, is_admin: bool = False):
    senha_hash = _hash_password(password)
    execute("INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)", (email.strip().lower(), senha_hash, 1 if is_admin else 0))
    row = fetch_one("SELECT id FROM users WHERE email = ?", (email.strip().lower(),))
    novo_id = row["id"] if row else None
    if novo_id is not None: seed_categorias_padrao(novo_id)
    return novo_id

def get_user_by_email(email: str):
    return fetch_one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))

def get_user_by_id(user_id: int):
    return fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

EMAIL_USUARIO_PADRAO = "local@financas.app"

def obter_ou_criar_usuario_padrao():
    u = get_user_by_email(EMAIL_USUARIO_PADRAO)
    if not u:
        senha_aleatoria = secrets.token_urlsafe(24)
        create_user(EMAIL_USUARIO_PADRAO, senha_aleatoria, is_admin=True)
        u = get_user_by_email(EMAIL_USUARIO_PADRAO)
    return {k: v for k, v in u.items() if k != "password_hash"}

def authenticate_user(email: str, password: str):
    u = get_user_by_email(email)
    if not u: return None
    if _verify_password(password, u["password_hash"]):
        u_safe = {k: v for k, v in u.items() if k != "password_hash"}
        return u_safe
    return None

def set_user_password(user_id: int, new_password: str):
    execute("UPDATE users SET password_hash = ? WHERE id = ?", (_hash_password(new_password), user_id))

def _gerar_codigo_reset() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))

def _can_access_record(requesting_user, record_user_id) -> bool:
    if requesting_user is None: return False
    if requesting_user.get("id") == record_user_id: return True
    return False

def _execute_autocura_unique(sql: str, params, tabela: str, funcao_migracao):
    try: execute(sql, params)
    except Exception as e:
        if "unique" in str(e).lower():
            funcao_migracao()
            execute(sql, params)
        else: raise

def add_categoria(nome: str, teto_mensal: float = 0.0, user_id: int = None):
    _execute_autocura_unique("INSERT INTO categorias (nome, teto_mensal, user_id) VALUES (?, ?, ?)", (nome.strip(), teto_mensal, user_id), "categorias", _migrar_categorias_remover_unique_global)

def list_categorias(requesting_user: dict = None):
    if not requesting_user: return []
    return fetch_all("SELECT * FROM categorias WHERE user_id = ? ORDER BY nome", (requesting_user.get("id"),))

def update_categoria_teto(categoria_id: int, teto_mensal: float, requesting_user: dict):
    before = fetch_one("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")): raise PermissionError("Sem permissão.")
    execute("UPDATE categorias SET teto_mensal = ? WHERE id = ?", (teto_mensal, categoria_id))

class RegistroVinculadoError(Exception): pass

def delete_categoria(categoria_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM categorias WHERE id = ?", (categoria_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")): raise PermissionError("Sem permissão.")
    execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))

def add_cartao(nome: str, dia_fechamento: int, dia_vencimento: int, banco: str = None, user_id: int = None):
    _execute_autocura_unique("INSERT INTO cartoes (nome, dia_fechamento, dia_vencimento, banco, user_id) VALUES (?, ?, ?, ?, ?)", (nome.strip(), dia_fechamento, dia_vencimento, banco, user_id), "cartoes", _migrar_cartoes_remover_unique_global)

def list_cartoes(requesting_user: dict = None):
    if not requesting_user: return []
    return fetch_all("SELECT * FROM cartoes WHERE user_id = ? ORDER BY nome", (requesting_user.get("id"),))

def delete_cartao(cartao_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM cartoes WHERE id = ?", (cartao_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")): raise PermissionError("Sem permissão.")
    execute("DELETE FROM cartoes WHERE id = ?", (cartao_id,))

def add_receita(data_str: str, origem: str, valor: float, observacao: str = "", user_id: int = None):
    execute("INSERT INTO receitas (data, origem, valor, observacao, user_id) VALUES (?, ?, ?, ?, ?)", (data_str, origem, valor, observacao, user_id))

def list_receitas(requesting_user: dict = None, ano: int = None, mes: int = None):
    if not requesting_user: return []
    sql = "SELECT * FROM receitas WHERE user_id = ?"
    params = [requesting_user.get("id")]
    if ano is not None:
        sql += " AND strftime('%Y', data) = ?"
        params.append(f"{ano:04d}")
    if mes is not None:
        sql += " AND strftime('%m', data) = ?"
        params.append(f"{mes:02d}")
    sql += " ORDER BY data DESC"
    return fetch_all(sql, params)

def delete_receita(receita_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM receitas WHERE id = ?", (receita_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")): raise PermissionError("Sem permissão.")
    execute("DELETE FROM receitas WHERE id = ?", (receita_id,))

def calcular_primeira_competencia(data_compra: date, forma_pagamento: str, cartao_row=None) -> date:
    if forma_pagamento == "Cartão de Crédito" and cartao_row is not None:
        if data_compra.day > cartao_row["dia_fechamento"]:
            return add_months(date(data_compra.year, data_compra.month, 1), 1)
        else:
            return date(data_compra.year, data_compra.month, 1)
    return date(data_compra.year, data_compra.month, 1)

def add_despesa(data_compra: date, categoria_id: int, descricao: str, valor_total: float,
                forma_pagamento: str, cartao_id: int = None, parcelas: int = 1, primeira_competencia: date = None, user_id: int = None):
    """
    Registra uma despesa e permite forçar a data de vencimento da 1ª parcela.
    """
    if primeira_competencia is None:
        cartao_row = fetch_one("SELECT * FROM cartoes WHERE id = ?", (cartao_id,)) if cartao_id else None
        primeira_competencia = calcular_primeira_competencia(data_compra, forma_pagamento, cartao_row)

    parcelas = max(1, int(parcelas))
    valor_parcela = round(valor_total / parcelas, 2)
    soma_parcelas = round(valor_parcela * parcelas, 2)
    diferenca_arredondamento = round(valor_total - soma_parcelas, 2)

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

def list_despesas(requesting_user: dict = None, ano: int = None, mes: int = None):
    if not requesting_user: return []
    sql = """
        SELECT d.*, c.nome AS categoria_nome, ca.nome AS cartao_nome
        FROM despesas d LEFT JOIN categorias c ON d.categoria_id = c.id LEFT JOIN cartoes ca ON d.cartao_id = ca.id
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
    return fetch_all(sql, params)

def list_compras_por_tipo(requesting_user: dict = None, forma_pagamento: str = None, somente_parceladas: bool = None, referencia: date = None):
    if not requesting_user: return []
    referencia = referencia or date.today()
    ref_competencia = date(referencia.year, referencia.month, 1)

    sql = """
        SELECT d.*, c.nome AS categoria_nome, ca.nome AS cartao_nome
        FROM despesas d LEFT JOIN categorias c ON d.categoria_id = c.id LEFT JOIN cartoes ca ON d.cartao_id = ca.id
        WHERE d.user_id = ?
    """
    params = [requesting_user.get("id")]
    if forma_pagamento:
        sql += " AND d.forma_pagamento = ?"
        params.append(forma_pagamento)
    sql += " ORDER BY d.compra_grupo, d.parcela_atual"

    linhas = fetch_all(sql, params)
    grupos = {}
    for row in linhas:
        grupos.setdefault(row["compra_grupo"], []).append(row)

    resultado = []
    for grupo, rows in grupos.items():
        rows_ordenadas = sorted(rows, key=lambda r: r["parcela_atual"])
        primeira = rows_ordenadas[0]
        parcela_total = primeira["parcela_total"]

        if somente_parceladas is True and parcela_total <= 1: continue
        if somente_parceladas is False and parcela_total > 1: continue

        valor_pago = 0.0
        valor_restante = 0.0
        parcelas_pagas = 0
        for r in rows_ordenadas:
            comp = datetime.strptime(r["data_competencia"], "%Y-%m-%d").date()
            comp = date(comp.year, comp.month, 1)
            if comp <= ref_competencia:
                valor_pago = round(valor_pago + r["valor"], 2)
                parcelas_pagas += 1
            else:
                valor_restante = round(valor_restante + r["valor"], 2)

        parcelas_pagas = min(parcelas_pagas, parcela_total)
        parcelas_restantes = max(parcela_total - parcelas_pagas, 0)
        valor_total = round(valor_pago + valor_restante, 2)
        valor_parcela = round(valor_total / parcela_total, 2) if parcela_total else 0.0

        resultado.append({
            "compra_grupo": grupo, "descricao": primeira["descricao"], "categoria_nome": primeira["categoria_nome"],
            "cartao_nome": primeira["cartao_nome"], "forma_pagamento": primeira["forma_pagamento"], "data_compra": primeira["data_compra"],
            "valor_total": valor_total, "valor_parcela": valor_parcela, "parcela_total": parcela_total,
            "parcelas_pagas": parcelas_pagas, "parcelas_restantes": parcelas_restantes, "valor_pago": valor_pago,
            "valor_restante": valor_restante, "concluido": parcelas_restantes == 0,
        })
    resultado.sort(key=lambda x: (x["concluido"], -x["parcelas_restantes"]))
    return resultado

def list_parcelamentos(requesting_user: dict = None, referencia: date = None):
    return list_compras_por_tipo(requesting_user, forma_pagamento="Cartão de Crédito", somente_parceladas=True, referencia=referencia)

def delete_despesa(despesa_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM despesas WHERE id = ?", (despesa_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")): raise PermissionError("Sem permissão.")
    execute("DELETE FROM despesas WHERE id = ?", (despesa_id,))

def delete_grupo(compra_grupo: str, requesting_user: dict):
    rows = fetch_all("SELECT * FROM despesas WHERE compra_grupo = ?", (compra_grupo,))
    for r in rows:
        if not _can_access_record(requesting_user, r.get("user_id")): raise PermissionError("Sem permissão.")
    execute("DELETE FROM despesas WHERE compra_grupo = ?", (compra_grupo,))

def add_despesa_fixa(descricao: str, categoria_id: int, valor: float, forma_pagamento: str, cartao_id: int = None, dia_vencimento: int = 1, user_id: int = None):
    _execute_autocura_unique(
        "INSERT INTO despesas_fixas (descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, ativa, user_id) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, user_id), "despesas_fixas", _migrar_despesas_fixas_remover_unique_global
    )

def list_despesas_fixas(requesting_user: dict = None, somente_ativas: bool = False):
    if not requesting_user: return []
    sql = "SELECT df.*, c.nome AS categoria_nome FROM despesas_fixas df LEFT JOIN categorias c ON df.categoria_id = c.id WHERE df.user_id = ?"
    params = [requesting_user.get("id")]
    if somente_ativas: sql += " AND ativa = 1"
    sql += " ORDER BY df.descricao"
    return fetch_all(sql, params)

def set_despesa_fixa_ativa(fixa_id: int, ativa: bool, requesting_user: dict):
    before = fetch_one("SELECT * FROM despesas_fixas WHERE id = ?", (fixa_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")): raise PermissionError("Sem permissão.")
    execute("UPDATE despesas_fixas SET ativa = ? WHERE id = ?", (1 if ativa else 0, fixa_id))

def delete_despesa_fixa(fixa_id: int, requesting_user: dict):
    before = fetch_one("SELECT * FROM despesas_fixas WHERE id = ?", (fixa_id,))
    if not before or not _can_access_record(requesting_user, before.get("user_id")): raise PermissionError("Sem permissão.")
    execute("UPDATE despesas SET fixa_origem_id = NULL WHERE fixa_origem_id = ?", (fixa_id,))
    execute("DELETE FROM despesas_fixas WHERE id = ?", (fixa_id,))

def gerar_despesas_fixas_do_mes(ano: int, mes: int, requesting_user: dict = None):
    competencia = date(ano, mes, 1).isoformat()
    criados = 0
    fixas = list_despesas_fixas(requesting_user, somente_ativas=True)
    for f in fixas:
        ja_existe = fetch_one("SELECT COUNT(*) AS n FROM despesas WHERE fixa_origem_id = ? AND data_competencia = ?", (f["id"], competencia))["n"]
        if ja_existe: continue
        dia = min(f.get("dia_vencimento") or 1, calendar.monthrange(ano, mes)[1])
        data_ocorrencia = date(ano, mes, dia)
        execute("""
            INSERT INTO despesas (data_compra, data_competencia, categoria_id, descricao, valor, forma_pagamento, cartao_id, parcela_atual, parcela_total, compra_grupo, fixa, fixa_origem_id, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, 1, ?, ?)
        """, (data_ocorrencia.isoformat(), competencia, f["categoria_id"], f["descricao"], f["valor"], f["forma_pagamento"], f["cartao_id"], str(uuid.uuid4()), f["id"], f.get("user_id")))
        criados += 1
    return criados

def get_reserva_percentual() -> float:
    row = fetch_one("SELECT reserva_percentual FROM config WHERE id = 1")
    return row["reserva_percentual"] if row else 0.0

def set_reserva_percentual(percentual: float):
    execute("UPDATE config SET reserva_percentual = ? WHERE id = 1", (percentual,))

def get_audit_logs(limit: int = 200):
    return fetch_all("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))

if __name__ == "__main__":
    init_db()
