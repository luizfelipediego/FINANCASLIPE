# -*- coding: utf-8 -*-
"""
utils.py
========
Funções auxiliares: formatação de moeda, nomes de meses em português
e cálculo do resumo (balanço) financeiro de um mês específico.
"""

import pandas as pd
import db

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
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
