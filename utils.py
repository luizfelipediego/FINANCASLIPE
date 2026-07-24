# -*- coding: utf-8 -*-
"""
utils.py
========
Funções auxiliares: formatação de moeda, nomes de meses em português,
dicionário de bancos (com selo colorido/emoji) e cálculo do resumo (balanço)
financeiro de um mês específico.

OBS. SOBRE OS "SÍMBOLOS DOS BANCOS":
As logomarcas oficiais de Itaú, Bradesco, Santander, Nubank etc. são marcas
registradas de cada instituição, protegidas por direito de propriedade
intelectual — não é possível reproduzir os logos reais aqui. Em vez disso,
foi criado um selo estilizado (emoji colorido + sigla/nome do banco) só para
facilitar a identificação visual dos cartões cadastrados, sem usar nenhuma
marca oficial.
"""
import pandas as pd
import db

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

# ---------------------------------------------------------------------------
# Selos estilizados por banco (emoji + nome) — NÃO são as logomarcas oficiais,
# apenas um selo colorido para diferenciar visualmente cada instituição.
# 12 bancos/fintechs mais comuns no Brasil.
# ---------------------------------------------------------------------------
BANCOS_EMOJI = {
    "Itaú":               "🟠 Itaú",
    "Bradesco":           "🔴 Bradesco",
    "Santander":          "🔺 Santander",
    "Banco do Brasil":    "🟡 Banco do Brasil",
    "Caixa Econômica":    "🔵 Caixa Econômica",
    "Nubank":             "🟣 Nubank",
    "Inter":              "🧡 Inter",
    "C6 Bank":            "⚫ C6 Bank",
    "PicPay":             "🟢 PicPay",
    "Mercado Pago":       "🩵 Mercado Pago",
    "BTG Pactual":        "⚪ BTG Pactual",
    "Sicoob/Sicredi":     "🟢 Sicoob/Sicredi",
    "Next":               "🟩 Next",
    "Outro":              "⚪ Outro",
}


def formatar_moeda(valor: float) -> str:
    """Formata um número no padrão monetário brasileiro: R$ 1.234,56"""
    if valor is None:
        valor = 0
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
    return f"R$ {texto}"


def despesas_para_dataframe(despesas) -> pd.DataFrame:
    cols = ["id", "data_compra", "data_competencia", "categoria_nome", "descricao",
            "valor", "forma_pagamento", "cartao_nome", "parcela_atual", "parcela_total",
            "fixa", "compra_grupo"]
    if not despesas:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([dict(d) for d in despesas])[cols]


def receitas_para_dataframe(receitas) -> pd.DataFrame:
    cols = ["id", "data", "origem", "valor", "observacao"]
    if not receitas:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([dict(r) for r in receitas])[cols]


def cartoes_para_dataframe(cartoes) -> pd.DataFrame:
    cols = ["id", "banco", "nome", "dia_fechamento", "dia_vencimento"]
    if not cartoes:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame([dict(c) for c in cartoes])
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


def calcular_resumo_mensal(ano: int, mes: int) -> dict:
    """
    Calcula o balanço do mês:
    - Total de Receitas
    - Total de Despesas (fixas + parcelas que caem na competência do mês)
    - Valor destinado à Reserva (% configurado sobre as receitas do mês)
    - Saldo Livre Líquido = Receitas - Despesas - Reserva
    """
    receitas = db.list_receitas(ano, mes)
    despesas = db.list_despesas(ano, mes)
    total_receitas = sum(r["valor"] for r in receitas)
    total_despesas = sum(d["valor"] for d in despesas)
    percentual_reserva = db.get_reserva_percentual()
    valor_reserva = round(total_receitas * percentual_reserva / 100, 2)
    saldo_livre = round(total_receitas - total_despesas - valor_reserva, 2)
    return {
        "total_receitas": total_receitas,
        "total_despesas": total_despesas,
        "percentual_reserva": percentual_reserva,
        "valor_reserva": valor_reserva,
        "saldo_livre": saldo_livre,
        "receitas": receitas,
        "despesas": despesas,
    }


def cor_status_teto(percentual: float) -> str:
    """Retorna uma cor (hex) de acordo com o percentual do teto de gastos atingido."""
    if percentual >= 100:
        return "#e74c3c"   # vermelho
    elif percentual >= 80:
        return "#f39c12"   # laranja
    else:
        return "#2ecc71"   # verde
# -*- coding: utf-8 -*-
"""
utils.py
========
Funções auxiliares de segurança e e-mail para autenticação.
"""
from __future__ import annotations

import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

try:
    import bcrypt
except Exception:
    bcrypt = None

TOKEN_TTL_MINUTES = 30
OTP_DIGITS = 6


def _secret(key: str, default=None):
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


def hash_password(password: str) -> str:
    if bcrypt is None:
        raise RuntimeError('bcrypt não instalado. Instale com pip install bcrypt')
    if not password:
        raise ValueError('Senha vazia')
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    if bcrypt is None:
        raise RuntimeError('bcrypt não instalado. Instale com pip install bcrypt')
    if not password or not password_hash:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def generate_verification_token() -> str:
    return secrets.token_urlsafe(32)


def generate_otp() -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(OTP_DIGITS))


def token_expires_at(minutes: int = TOKEN_TTL_MINUTES) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def is_token_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return True
    try:
        dt = datetime.fromisoformat(expires_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= dt
    except Exception:
        return True


def send_email(to_email: str, subject: str, body: str) -> None:
    host = _secret('SMTP_HOST')
    port = int(_secret('SMTP_PORT', 58
