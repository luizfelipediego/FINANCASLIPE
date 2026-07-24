
Db · PY
# -*- coding: utf-8 -*-
"""
db.py
=====
Camada de acesso a dados do Sistema de Gestão Financeira Pessoal e Familiar.
 
Suporta DOIS modos de operação, escolhidos automaticamente:
 
1) MODO NUVEM (recomendado para produção / Streamlit Community Cloud):
   Se as credenciais do Turso (TURSO_DATABASE_URL e TURSO_AUTH_TOKEN) estiverem
   configuradas (em st.secrets ou variáveis de ambiente), todos os dados são
   gravados diretamente em um banco Turso (compatível com SQLite, hospedado na
   nuvem). Como nada é gravado apenas no disco do servidor, os dados NUNCA se
   perdem quando o app reinicia ou é redeployado.
 
2) MODO LOCAL (padrão para desenvolvimento na sua máquina):
   Se as credenciais não existirem, o sistema usa um arquivo SQLite local
   (financas.db), como antes — ótimo para testar sem precisar de internet.
 
Todas as regras de negócio (parcelamento, competência de cartão de crédito,
despesas fixas, reserva automática) continuam centralizadas aqui.
"""
 
import os
import sqlite3
import uuid
import calendar
from datetime import date
from contextlib import contextmanager
 
DB_PATH = "financas.db"
 
 
# ---------------------------------------------------------------------------
# Configuração de credenciais (Turso / nuvem) e seleção automática de backend
# ---------------------------------------------------------------------------
 
def _get_secret(key: str):
    """
    Busca uma credencial primeiro em st.secrets (Streamlit Cloud) e, se não
    encontrar, em variáveis de ambiente (útil para outros tipos de hospedagem).
    """
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
 
 
@contextmanager
def get_connection():
    """
    Context manager que abre a conexão correta (nuvem ou local), garante
    commit ao final do bloco e fecha a conexão adequadamente.
    """
    if usando_banco_em_nuvem():
        import libsql
        conn = libsql.connect(
            database=_get_secret("TURSO_DATABASE_URL"),
            auth_token=_get_secret("TURSO_AUTH_TOKEN"),
        )
    else:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
 
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
 
 
# ---------------------------------------------------------------------------
# Helpers para converter resultados de query em dicionários (independente do
# backend usado, evitando depender de comportamento de row_factory específico
# de cada driver).
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
 
 
def query_all(conn, sql: str, params=()) -> list:
    """Executa um SELECT e retorna uma lista de dicts (uma por linha)."""
    cur = conn.execute(sql, params)
    return _rows_to_dicts(cur, cur.fetchall())
 
 
def query_one(conn, sql: str, params=()):
    """Executa um SELECT e retorna um único dict (ou None)."""
    cur = conn.execute(sql, params)
    return _row_to_dict(cur, cur.fetchone())
 
 
# ---------------------------------------------------------------------------
# Inicialização do schema
# ---------------------------------------------------------------------------
 
def init_db():
    """Cria todas as tabelas do sistema, caso ainda não existam."""
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            teto_mensal REAL DEFAULT 0
        )
        """)
 
        conn.execute("""
        CREATE TABLE IF NOT EXISTS cartoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            dia_fechamento INTEGER NOT NULL,
            dia_vencimento INTEGER NOT NULL
        )
        """)
 
        conn.execute("""
        CREATE TABLE IF NOT EXISTS receitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            origem TEXT NOT NULL,
            valor REAL NOT NULL,
            observacao TEXT
        )
        """)
 
        conn.execute("""
        CREATE TABLE IF NOT EXISTS despesas_fixas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            categoria_id INTEGER,
            valor REAL NOT NULL,
            forma_pagamento TEXT NOT NULL,
            cartao_id INTEGER,
            dia_vencimento INTEGER DEFAULT 1,
            ativa INTEGER DEFAULT 1,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id),
            FOREIGN KEY (cartao_id) REFERENCES cartoes(id)
        )
        """)
 
        conn.execute("""
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
            FOREIGN KEY (categoria_id) REFERENCES categorias(id),
            FOREIGN KEY (cartao_id) REFERENCES cartoes(id),
            FOREIGN KEY (fixa_origem_id) REFERENCES despesas_fixas(id)
        )
        """)
 
        conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY,
            reserva_percentual REAL DEFAULT 10
        )
        """)
        conn.execute("INSERT OR IGNORE INTO config (id, reserva_percentual) VALUES (1, 10)")
 
        total_categorias = query_one(conn, "SELECT COUNT(*) AS n FROM categorias")["n"]
        if total_categorias == 0:
            padrao = ["Mercado", "Saúde/Remédios", "Estudos/Educação",
                      "Lazer", "Moradia", "Veículo", "Outros"]
            for nome in padrao:
                conn.execute("INSERT INTO categorias (nome, teto_mensal) VALUES (?, 0)", (nome,))
 
 
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
# Categorias
# ---------------------------------------------------------------------------
 
def add_categoria(nome: str, teto_mensal: float = 0.0):
    with get_connection() as conn:
        conn.execute("INSERT INTO categorias (nome, teto_mensal) VALUES (?, ?)",
                     (nome.strip(), teto_mensal))
 
 
def list_categorias():
    with get_connection() as conn:
        return query_all(conn, "SELECT * FROM categorias ORDER BY nome")
 
 
def update_categoria_teto(categoria_id: int, teto_mensal: float):
    with get_connection() as conn:
        conn.execute("UPDATE categorias SET teto_mensal = ? WHERE id = ?",
                     (teto_mensal, categoria_id))
 
 
def delete_categoria(categoria_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
 
 
# ---------------------------------------------------------------------------
# Cartões de crédito
# ---------------------------------------------------------------------------
 
def add_cartao(nome: str, dia_fechamento: int, dia_vencimento: int):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO cartoes (nome, dia_fechamento, dia_vencimento) VALUES (?, ?, ?)",
            (nome.strip(), dia_fechamento, dia_vencimento)
        )
 
 
def list_cartoes():
    with get_connection() as conn:
        return query_all(conn, "SELECT * FROM cartoes ORDER BY nome")
 
 
def delete_cartao(cartao_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM cartoes WHERE id = ?", (cartao_id,))
 
 
# ---------------------------------------------------------------------------
# Receitas (entradas)
# ---------------------------------------------------------------------------
 
def add_receita(data_str: str, origem: str, valor: float, observacao: str = ""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO receitas (data, origem, valor, observacao) VALUES (?, ?, ?, ?)",
            (data_str, origem, valor, observacao)
        )
 
 
def list_receitas(ano: int = None, mes: int = None):
    sql = "SELECT * FROM receitas"
    params = []
    conds = []
    if ano is not None:
        conds.append("strftime('%Y', data) = ?")
        params.append(f"{ano:04d}")
    if mes is not None:
        conds.append("strftime('%m', data) = ?")
        params.append(f"{mes:02d}")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY data DESC"
    with get_connection() as conn:
        return query_all(conn, sql, params)
 
 
def delete_receita(receita_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM receitas WHERE id = ?", (receita_id,))
 
 
# ---------------------------------------------------------------------------
# Despesas: lançamento avulso / parcelado / cartão de crédito
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
                forma_pagamento: str, cartao_id: int = None, parcelas: int = 1):
    """
    Registra uma despesa (à vista ou parcelada) gerando automaticamente
    uma linha por parcela, já projetada nos meses futuros corretos.
    """
    cartao_row = None
    if cartao_id:
        with get_connection() as conn:
            cartao_row = query_one(conn, "SELECT * FROM cartoes WHERE id = ?", (cartao_id,))
 
    primeira_competencia = calcular_primeira_competencia(data_compra, forma_pagamento, cartao_row)
 
    parcelas = max(1, int(parcelas))
    valor_parcela = round(valor_total / parcelas, 2)
    soma_parcelas = round(valor_parcela * parcelas, 2)
    diferenca_arredondamento = round(valor_total - soma_parcelas, 2)  # ajustada na última parcela
 
    grupo = str(uuid.uuid4())
 
    with get_connection() as conn:
        for i in range(parcelas):
            competencia_i = add_months(primeira_competencia, i)
            valor_i = valor_parcela
            if i == parcelas - 1:
                valor_i = round(valor_i + diferenca_arredondamento, 2)
 
            conn.execute("""
                INSERT INTO despesas
                (data_compra, data_competencia, categoria_id, descricao, valor,
                 forma_pagamento, cartao_id, parcela_atual, parcela_total,
                 compra_grupo, fixa, fixa_origem_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
            """, (
                data_compra.isoformat(), competencia_i.isoformat(), categoria_id, descricao,
                valor_i, forma_pagamento, cartao_id, i + 1, parcelas, grupo
            ))
 
 
def list_despesas(ano: int = None, mes: int = None):
    """Lista despesas filtrando pela COMPETÊNCIA (mês em que a parcela efetivamente pesa no orçamento)."""
    sql = """
        SELECT d.*, c.nome AS categoria_nome, ca.nome AS cartao_nome
        FROM despesas d
        LEFT JOIN categorias c ON d.categoria_id = c.id
        LEFT JOIN cartoes ca ON d.cartao_id = ca.id
    """
    conds, params = [], []
    if ano is not None:
        conds.append("strftime('%Y', d.data_competencia) = ?")
        params.append(f"{ano:04d}")
    if mes is not None:
        conds.append("strftime('%m', d.data_competencia) = ?")
        params.append(f"{mes:02d}")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY d.data_competencia DESC, d.data_compra DESC"
    with get_connection() as conn:
        return query_all(conn, sql, params)
 
 
def delete_despesa(despesa_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM despesas WHERE id = ?", (despesa_id,))
 
 
def delete_grupo(compra_grupo: str):
    """Apaga todas as parcelas de uma mesma compra."""
    with get_connection() as conn:
        conn.execute("DELETE FROM despesas WHERE compra_grupo = ?", (compra_grupo,))
 
 
# ---------------------------------------------------------------------------
# Despesas fixas / recorrentes
# ---------------------------------------------------------------------------
 
def add_despesa_fixa(descricao: str, categoria_id: int, valor: float, forma_pagamento: str,
                      cartao_id: int = None, dia_vencimento: int = 1):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO despesas_fixas
            (descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento, ativa)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (descricao, categoria_id, valor, forma_pagamento, cartao_id, dia_vencimento))
 
 
def list_despesas_fixas(somente_ativas: bool = False):
    sql = "SELECT df.*, c.nome AS categoria_nome FROM despesas_fixas df LEFT JOIN categorias c ON df.categoria_id = c.id"
    if somente_ativas:
        sql += " WHERE ativa = 1"
    sql += " ORDER BY df.descricao"
    with get_connection() as conn:
        return query_all(conn, sql)
 
 
def set_despesa_fixa_ativa(fixa_id: int, ativa: bool):
    with get_connection() as conn:
        conn.execute("UPDATE despesas_fixas SET ativa = ? WHERE id = ?", (1 if ativa else 0, fixa_id))
 
 
def delete_despesa_fixa(fixa_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM despesas_fixas WHERE id = ?", (fixa_id,))
 
 
def gerar_despesas_fixas_do_mes(ano: int, mes: int):
    """
    Duplica automaticamente todas as despesas fixas ativas para o mês/ano informado,
    evitando duplicidade caso já tenham sido geradas anteriormente.
    Retorna a quantidade de lançamentos criados.
    """
    competencia = date(ano, mes, 1).isoformat()
    criados = 0
    with get_connection() as conn:
        fixas = query_all(conn, "SELECT * FROM despesas_fixas WHERE ativa = 1")
        for f in fixas:
            ja_existe = query_one(conn, """
                SELECT COUNT(*) AS n FROM despesas
                WHERE fixa_origem_id = ? AND data_competencia = ?
            """, (f["id"], competencia))["n"]
 
            if ja_existe:
                continue
 
            dia = min(f["dia_vencimento"] or 1, calendar.monthrange(ano, mes)[1])
            data_ocorrencia = date(ano, mes, dia)
 
            conn.execute("""
                INSERT INTO despesas
                (data_compra, data_competencia, categoria_id, descricao, valor,
                 forma_pagamento, cartao_id, parcela_atual, parcela_total,
                 compra_grupo, fixa, fixa_origem_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, 1, ?)
            """, (
                data_ocorrencia.isoformat(), competencia, f["categoria_id"], f["descricao"],
                f["valor"], f["forma_pagamento"], f["cartao_id"], str(uuid.uuid4()), f["id"]
            ))
            criados += 1
    return criados
 
 
# ---------------------------------------------------------------------------
# Configurações (reserva / aporte)
# ---------------------------------------------------------------------------
 
def get_reserva_percentual() -> float:
    with get_connection() as conn:
        row = query_one(conn, "SELECT reserva_percentual FROM config WHERE id = 1")
        return row["reserva_percentual"] if row else 0.0
 
 
def set_reserva_percentual(percentual: float):
    with get_connection() as conn:
        conn.execute("UPDATE config SET reserva_percentual = ? WHERE id = 1", (percentual,))
 
