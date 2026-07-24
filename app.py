# -*- coding: utf-8 -*-
"""
app.py
======
Sistema de Gestão Financeira Pessoal e Familiar
------------------------------------------------
Interface construída em Streamlit. Toda a persistência é feita em SQLite (db.py)
e as regras de negócio (parcelamento, competência de cartão, despesas fixas,
reserva automática e orçamento por categoria) estão implementadas em db.py / utils.py.

Para executar:
    streamlit run app.py
"""

from datetime import date
import io

import pandas as pd
import plotly.express as px
import streamlit as st

import db
import utils

# ---------------------------------------------------------------------------
# Configuração inicial
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Gestão Financeira Familiar", page_icon="💰", layout="wide")
db.init_db()

FORMAS_PAGAMENTO = ["PIX", "Cartão de Crédito", "Cartão de Débito", "Dinheiro", "Transferência"]
ORIGENS_RECEITA = ["Trabalho principal", "Renda Extra", "Rendimentos", "Outros"]

HOJE = date.today()

# ---------------------------------------------------------------------------
# Sidebar / navegação
# ---------------------------------------------------------------------------

st.sidebar.title("💰 Finanças da Família")
pagina = st.sidebar.radio(
    "Navegação",
    [
        "📊 Dashboard",
        "📥 Receitas",
        "📤 Despesas",
        "🔁 Despesas Fixas",
        "💳 Cartões",
        "🏷️ Categorias e Orçamento",
        "📁 Relatórios e Exportação",
        "⚙️ Configurações",
    ],
)

st.sidebar.markdown("---")
ano_sel = st.sidebar.selectbox("Ano de referência", list(range(HOJE.year - 3, HOJE.year + 2)),
                                index=3)
mes_sel = st.sidebar.selectbox("Mês de referência", list(range(1, 13)),
                                index=HOJE.month - 1,
                                format_func=lambda m: utils.MESES_PT[m])
st.sidebar.caption("Esse período é usado no Dashboard, Relatórios e Orçamento.")


# ---------------------------------------------------------------------------
# Página: DASHBOARD
# ---------------------------------------------------------------------------

if pagina == "📊 Dashboard":
    st.title(f"📊 Dashboard — {utils.MESES_PT[mes_sel]}/{ano_sel}")

    resumo = utils.calcular_resumo_mensal(ano_sel, mes_sel)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de Receitas", utils.formatar_moeda(resumo["total_receitas"]))
    col2.metric("Total de Despesas", utils.formatar_moeda(resumo["total_despesas"]))
    col3.metric(f"Reserva ({resumo['percentual_reserva']:.1f}%)",
                utils.formatar_moeda(resumo["valor_reserva"]))
    col4.metric("Saldo Livre Líquido", utils.formatar_moeda(resumo["saldo_livre"]),
                delta=None if resumo["saldo_livre"] >= 0 else "Atenção: negativo")

    st.markdown("---")

    col_a, col_b = st.columns(2)

    # Gráfico de distribuição por categoria (mês atual)
    with col_a:
        st.subheader("Distribuição de Despesas por Categoria")
        df_desp = utils.despesas_para_dataframe(resumo["despesas"])
        if not df_desp.empty:
            df_group = df_desp.groupby("categoria_nome", as_index=False)["valor"].sum()
            fig = px.pie(df_group, names="categoria_nome", values="valor", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma despesa lançada nesta competência.")

    # Evolução mensal de saldo (últimos 12 meses até o período selecionado)
    with col_b:
        st.subheader("Evolução Mensal do Saldo")
        historico = []
        for i in range(11, -1, -1):
            d = db.add_months(date(ano_sel, mes_sel, 1), -i)
            r = utils.calcular_resumo_mensal(d.year, d.month)
            historico.append({
                "mes": f"{utils.MESES_PT[d.month][:3]}/{str(d.year)[2:]}",
                "Saldo Livre": r["saldo_livre"],
                "Receitas": r["total_receitas"],
                "Despesas": r["total_despesas"],
            })
        df_hist = pd.DataFrame(historico)
        fig2 = px.line(df_hist, x="mes", y=["Receitas", "Despesas", "Saldo Livre"], markers=True)
        fig2.update_layout(legend_title_text="", xaxis_title="", yaxis_title="R$")
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.subheader("🚦 Alertas de Teto de Gastos por Categoria")

    categorias = db.list_categorias()
    df_desp_cat = utils.despesas_para_dataframe(resumo["despesas"])
    algum_teto_definido = False

    for cat in categorias:
        if not cat["teto_mensal"] or cat["teto_mensal"] <= 0:
            continue
        algum_teto_definido = True
        gasto = df_desp_cat.loc[df_desp_cat["categoria_nome"] == cat["nome"], "valor"].sum() \
            if not df_desp_cat.empty else 0.0
        percentual = (gasto / cat["teto_mensal"]) * 100 if cat["teto_mensal"] else 0
        cor = utils.cor_status_teto(percentual)

        st.markdown(f"**{cat['nome']}** — {utils.formatar_moeda(gasto)} de "
                     f"{utils.formatar_moeda(cat['teto_mensal'])} ({percentual:.0f}%)")
        st.markdown(f"""
        <div style="background-color:#e0e0e0; border-radius:6px; height:14px; width:100%;">
            <div style="background-color:{cor}; width:{min(percentual,100)}%; height:14px; border-radius:6px;"></div>
        </div>
        """, unsafe_allow_html=True)
        if percentual >= 100:
            st.error(f"⚠️ Teto de **{cat['nome']}** ultrapassado!")
        elif percentual >= 80:
            st.warning(f"Atenção: **{cat['nome']}** já atingiu {percentual:.0f}% do teto.")
        st.write("")

    if not algum_teto_definido:
        st.info("Nenhum teto de gasto configurado ainda. Defina em '🏷️ Categorias e Orçamento'.")


# ---------------------------------------------------------------------------
# Página: RECEITAS
# ---------------------------------------------------------------------------

elif pagina == "📥 Receitas":
    st.title("📥 Receitas (Entradas)")

    with st.form("form_receita", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_receita = c1.date_input("Data", value=HOJE)
        origem = c2.selectbox("Origem", ORIGENS_RECEITA)
        valor = c3.number_input("Valor (R$)", min_value=0.0, step=50.0, format="%.2f")
        observacao = st.text_input("Observação (opcional)")
        enviado = st.form_submit_button("➕ Registrar Receita")
        if enviado:
            if valor <= 0:
                st.error("Informe um valor maior que zero.")
            else:
                db.add_receita(data_receita.isoformat(), origem, valor, observacao)
                perc = db.get_reserva_percentual()
                st.success(
                    f"Receita registrada! Reserva automática ({perc:.1f}%): "
                    f"{utils.formatar_moeda(valor * perc / 100)}"
                )

    st.markdown("---")
    st.subheader(f"Receitas de {utils.MESES_PT[mes_sel]}/{ano_sel}")
    receitas = db.list_receitas(ano_sel, mes_sel)
    df = utils.receitas_para_dataframe(receitas)
    if df.empty:
        st.info("Nenhuma receita lançada neste período.")
    else:
        df_show = df.copy()
        df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        id_excluir = st.selectbox("Excluir lançamento (selecione o ID)",
                                   [None] + df["id"].tolist())
        if id_excluir and st.button("🗑️ Excluir receita selecionada"):
            db.delete_receita(id_excluir)
            st.success("Receita excluída.")
            st.rerun()


# ---------------------------------------------------------------------------
# Página: DESPESAS
# ---------------------------------------------------------------------------

elif pagina == "📤 Despesas":
    st.title("📤 Despesas (Saídas)")

    categorias = db.list_categorias()
    cartoes = db.list_cartoes()
    nomes_categorias = {c["nome"]: c["id"] for c in categorias}
    nomes_cartoes = {c["nome"]: c["id"] for c in cartoes}

    with st.form("form_despesa", clear_on_submit=True):
        c1, c2 = st.columns(2)
        data_compra = c1.date_input("Data da compra/despesa", value=HOJE)
        descricao = c2.text_input("Descrição")

        c3, c4 = st.columns(2)
        categoria_nome = c3.selectbox("Categoria", list(nomes_categorias.keys()))
        forma_pagamento = c4.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO)

        cartao_nome = None
        if forma_pagamento in ("Cartão de Crédito", "Cartão de Débito"):
            if nomes_cartoes:
                cartao_nome = st.selectbox("Cartão utilizado", list(nomes_cartoes.keys()))
            else:
                st.warning("Nenhum cartão cadastrado. Cadastre em '💳 Cartões'.")

        c5, c6 = st.columns(2)
        valor_total = c5.number_input("Valor total (R$)", min_value=0.0, step=10.0, format="%.2f")
        parcelas = 1
        if forma_pagamento == "Cartão de Crédito":
            parcelas = c6.number_input("Quantidade de parcelas", min_value=1, max_value=48, value=1, step=1)

        enviado = st.form_submit_button("➕ Registrar Despesa")

        if enviado:
            if valor_total <= 0:
                st.error("Informe um valor maior que zero.")
            elif not descricao.strip():
                st.error("Informe uma descrição.")
            else:
                categoria_id = nomes_categorias.get(categoria_nome)
                cartao_id = nomes_cartoes.get(cartao_nome) if cartao_nome else None
                db.add_despesa(data_compra, categoria_id, descricao, valor_total,
                                forma_pagamento, cartao_id, parcelas)

                if parcelas > 1:
                    cartao_row = next((c for c in cartoes if c["id"] == cartao_id), None)
                    primeira = db.calcular_primeira_competencia(data_compra, forma_pagamento, cartao_row)
                    st.success(
                        f"Despesa parcelada em {parcelas}x registrada! "
                        f"1ª parcela na competência de {utils.MESES_PT[primeira.month]}/{primeira.year}."
                    )
                else:
                    st.success("Despesa registrada com sucesso!")

    st.markdown("---")
    st.subheader(f"Despesas — competência de {utils.MESES_PT[mes_sel]}/{ano_sel}")
    despesas = db.list_despesas(ano_sel, mes_sel)
    df = utils.despesas_para_dataframe(despesas)
    if df.empty:
        st.info("Nenhuma despesa nesta competência.")
    else:
        df_show = df.copy()
        df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
        df_show["parcela"] = df_show["parcela_atual"].astype(str) + "/" + df_show["parcela_total"].astype(str)
        df_show = df_show[["id", "data_compra", "categoria_nome", "descricao", "valor",
                            "forma_pagamento", "cartao_nome", "parcela"]]
        df_show.columns = ["ID", "Data Compra", "Categoria", "Descrição", "Valor",
                            "Pagamento", "Cartão", "Parcela"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        id_excluir = st.selectbox("Excluir lançamento (selecione o ID)", [None] + df["id"].tolist())
        if id_excluir:
            colx, coly = st.columns(2)
            if colx.button("🗑️ Excluir apenas esta parcela"):
                db.delete_despesa(id_excluir)
                st.success("Parcela excluída.")
                st.rerun()
            grupo = df.loc[df["id"] == id_excluir, "compra_grupo"].values[0]
            if coly.button("🗑️ Excluir TODAS as parcelas desta compra"):
                db.delete_grupo(grupo)
                st.success("Todas as parcelas da compra foram excluídas.")
                st.rerun()


# ---------------------------------------------------------------------------
# Página: DESPESAS FIXAS
# ---------------------------------------------------------------------------

elif pagina == "🔁 Despesas Fixas":
    st.title("🔁 Despesas Fixas / Recorrentes")
    st.caption("Ex.: Aluguel, Internet, Assinaturas. Gere os lançamentos do mês com um clique.")

    categorias = db.list_categorias()
    cartoes = db.list_cartoes()
    nomes_categorias = {c["nome"]: c["id"] for c in categorias}
    nomes_cartoes = {c["nome"]: c["id"] for c in cartoes}

    with st.form("form_fixa", clear_on_submit=True):
        c1, c2 = st.columns(2)
        descricao = c1.text_input("Descrição (ex: Aluguel)")
        categoria_nome = c2.selectbox("Categoria", list(nomes_categorias.keys()))

        c3, c4, c5 = st.columns(3)
        valor = c3.number_input("Valor mensal (R$)", min_value=0.0, step=10.0, format="%.2f")
        forma_pagamento = c4.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO)
        dia_vencimento = c5.number_input("Dia de vencimento", min_value=1, max_value=28, value=5)

        cartao_nome = None
        if forma_pagamento in ("Cartão de Crédito", "Cartão de Débito") and nomes_cartoes:
            cartao_nome = st.selectbox("Cartão", list(nomes_cartoes.keys()))

        enviado = st.form_submit_button("➕ Cadastrar Despesa Fixa")
        if enviado:
            if not descricao.strip() or valor <= 0:
                st.error("Preencha descrição e valor corretamente.")
            else:
                cartao_id = nomes_cartoes.get(cartao_nome) if cartao_nome else None
                db.add_despesa_fixa(descricao, nomes_categorias[categoria_nome], valor,
                                     forma_pagamento, cartao_id, dia_vencimento)
                st.success("Despesa fixa cadastrada!")

    st.markdown("---")
    st.subheader("Despesas fixas cadastradas")
    fixas = db.list_despesas_fixas()
    if not fixas:
        st.info("Nenhuma despesa fixa cadastrada.")
    else:
        df_fixas = pd.DataFrame([dict(f) for f in fixas])
        df_show = df_fixas[["id", "descricao", "categoria_nome", "valor",
                             "forma_pagamento", "dia_vencimento", "ativa"]].copy()
        df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
        df_show["ativa"] = df_show["ativa"].apply(lambda x: "✅ Ativa" if x else "⏸️ Pausada")
        df_show.columns = ["ID", "Descrição", "Categoria", "Valor", "Pagamento", "Dia Venc.", "Status"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        col1, col2, col3 = st.columns(3)
        id_alvo = col1.selectbox("Selecionar ID para ação", df_fixas["id"].tolist())
        if col2.button("⏸️ Pausar / ▶️ Reativar"):
            atual = df_fixas.loc[df_fixas["id"] == id_alvo, "ativa"].values[0]
            db.set_despesa_fixa_ativa(id_alvo, not atual)
            st.rerun()
        if col3.button("🗑️ Excluir cadastro"):
            db.delete_despesa_fixa(id_alvo)
            st.rerun()

    st.markdown("---")
    st.subheader(f"Gerar lançamentos do mês selecionado ({utils.MESES_PT[mes_sel]}/{ano_sel})")
    st.caption("Duplica automaticamente todas as despesas fixas ativas para este mês, "
               "sem gerar duplicidade se já tiverem sido geradas antes.")
    if st.button("🔁 Gerar Despesas Fixas do Mês"):
        qtd = db.gerar_despesas_fixas_do_mes(ano_sel, mes_sel)
        if qtd > 0:
            st.success(f"{qtd} lançamento(s) gerado(s) para {utils.MESES_PT[mes_sel]}/{ano_sel}.")
        else:
            st.info("Todos os lançamentos deste mês já haviam sido gerados anteriormente.")


# ---------------------------------------------------------------------------
# Página: CARTÕES
# ---------------------------------------------------------------------------

elif pagina == "💳 Cartões":
    st.title("💳 Gestão de Cartões de Crédito")

    with st.form("form_cartao", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nome = c1.text_input("Nome do cartão (ex: Nubank, Inter)")
        dia_fechamento = c2.number_input("Dia de fechamento da fatura", min_value=1, max_value=28, value=25)
        dia_vencimento = c3.number_input("Dia de vencimento da fatura", min_value=1, max_value=28, value=5)
        enviado = st.form_submit_button("➕ Cadastrar Cartão")
        if enviado:
            if not nome.strip():
                st.error("Informe o nome do cartão.")
            else:
                try:
                    db.add_cartao(nome, dia_fechamento, dia_vencimento)
                    st.success("Cartão cadastrado!")
                except Exception:
                    st.error("Já existe um cartão com esse nome.")

    st.markdown("---")
    cartoes = db.list_cartoes()
    if not cartoes:
        st.info("Nenhum cartão cadastrado ainda.")
    else:
        df = pd.DataFrame([dict(c) for c in cartoes])
        df.columns = ["ID", "Nome", "Dia Fechamento", "Dia Vencimento"]
        st.dataframe(df, use_container_width=True, hide_index=True)

        id_excluir = st.selectbox("Excluir cartão (ID)", [None] + [c["id"] for c in cartoes])
        if id_excluir and st.button("🗑️ Excluir cartão"):
            db.delete_cartao(id_excluir)
            st.rerun()

        st.info(
            "📌 **Regra de fechamento:** compras feitas *após* o dia de fechamento têm a "
            "1ª parcela lançada automaticamente na fatura (competência) do **mês seguinte**."
        )


# ---------------------------------------------------------------------------
# Página: CATEGORIAS E ORÇAMENTO
# ---------------------------------------------------------------------------

elif pagina == "🏷️ Categorias e Orçamento":
    st.title("🏷️ Categorias de Despesa e Teto de Gastos")

    with st.form("form_categoria", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nova categoria (ex: Pet, Viagem)")
        teto = c2.number_input("Teto mensal (R$) — opcional, 0 = sem limite", min_value=0.0, step=50.0)
        enviado = st.form_submit_button("➕ Adicionar Categoria")
        if enviado:
            if not nome.strip():
                st.error("Informe o nome da categoria.")
            else:
                try:
                    db.add_categoria(nome, teto)
                    st.success("Categoria criada!")
                except Exception:
                    st.error("Já existe uma categoria com esse nome.")

    st.markdown("---")
    st.subheader("Categorias cadastradas — defina/edite o teto mensal")
    categorias = db.list_categorias()
    for cat in categorias:
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.write(f"**{cat['nome']}**")
        novo_teto = col2.number_input(f"Teto (R$) — {cat['nome']}", min_value=0.0,
                                       value=float(cat["teto_mensal"] or 0), step=50.0,
                                       key=f"teto_{cat['id']}", label_visibility="collapsed")
        if col3.button("Salvar", key=f"salvar_{cat['id']}"):
            db.update_categoria_teto(cat["id"], novo_teto)
            st.success(f"Teto de {cat['nome']} atualizado!")
            st.rerun()

    st.markdown("---")
    id_excluir = st.selectbox("Excluir categoria (ID)", [None] + [c["id"] for c in categorias])
    if id_excluir and st.button("🗑️ Excluir categoria selecionada"):
        db.delete_categoria(id_excluir)
        st.rerun()


# ---------------------------------------------------------------------------
# Página: RELATÓRIOS E EXPORTAÇÃO
# ---------------------------------------------------------------------------

elif pagina == "📁 Relatórios e Exportação":
    st.title("📁 Relatórios, Filtros e Exportação")

    modo = st.radio("Visualizar por período:", ["Mensal", "Diário (dentro do mês)", "Anual"], horizontal=True)

    if modo == "Anual":
        receitas = db.list_receitas(ano_sel, None)
        despesas = db.list_despesas(ano_sel, None)
    else:
        receitas = db.list_receitas(ano_sel, mes_sel)
        despesas = db.list_despesas(ano_sel, mes_sel)

    df_r = utils.receitas_para_dataframe(receitas)
    df_d = utils.despesas_para_dataframe(despesas)

    if modo == "Diário (dentro do mês)" and not df_d.empty:
        dia_filtro = st.date_input("Selecione um dia específico (opcional)", value=None)
        if dia_filtro:
            df_d = df_d[df_d["data_compra"] == dia_filtro.isoformat()]
            df_r = df_r[df_r["data"] == dia_filtro.isoformat()] if not df_r.empty else df_r

    st.subheader("📥 Receitas")
    st.dataframe(df_r, use_container_width=True, hide_index=True)
    st.subheader("📤 Despesas")
    st.dataframe(df_d, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("⬇️ Exportar dados")

    col1, col2 = st.columns(2)
    with col1:
        csv_buffer = io.StringIO()
        df_export = pd.concat([
            df_r.assign(tipo="Receita"),
            df_d.rename(columns={"data_compra": "data"}).assign(tipo="Despesa")
        ], ignore_index=True, sort=False)
        df_export.to_csv(csv_buffer, index=False, sep=";", decimal=",")
        st.download_button("📄 Baixar CSV", data=csv_buffer.getvalue(),
                            file_name=f"financas_{ano_sel}_{mes_sel if modo != 'Anual' else 'ANO'}.csv",
                            mime="text/csv")

    with col2:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df_r.to_excel(writer, sheet_name="Receitas", index=False)
            df_d.to_excel(writer, sheet_name="Despesas", index=False)
        st.download_button("📊 Baixar Excel", data=excel_buffer.getvalue(),
                            file_name=f"financas_{ano_sel}_{mes_sel if modo != 'Anual' else 'ANO'}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# Página: CONFIGURAÇÕES
# ---------------------------------------------------------------------------

elif pagina == "⚙️ Configurações":
    st.title("⚙️ Configurações Gerais")

    st.subheader("🐷 Meta de Reserva / Investimentos")
    percentual_atual = db.get_reserva_percentual()
    novo_percentual = st.slider(
        "Percentual de todas as receitas do mês a ser destinado automaticamente à reserva:",
        min_value=0.0, max_value=100.0, value=float(percentual_atual), step=1.0
    )
    if st.button("💾 Salvar percentual de reserva"):
        db.set_reserva_percentual(novo_percentual)
        st.success(f"Reserva automática configurada para {novo_percentual:.1f}% das receitas.")

    st.markdown("---")
    st.subheader("🗄️ Status do Banco de Dados")
    if db.usando_banco_em_nuvem():
        st.success(db.get_backend_info())
    else:
        st.info(db.get_backend_info())
        st.caption(
            "Para ativar o banco em nuvem (Turso) e nunca mais perder dados ao reiniciar o app, "
            "configure TURSO_DATABASE_URL e TURSO_AUTH_TOKEN em `.streamlit/secrets.toml` "
            "(local) ou em 'Settings → Secrets' no Streamlit Community Cloud. "
            "Veja o passo a passo no README.md."
        )

    st.markdown("---")
    st.subheader("ℹ️ Sobre o sistema")
    st.write(
        "Sistema de Gestão Financeira Pessoal e Familiar — versão 1.1\n\n"
        "- Modo local: SQLite (`financas.db`) na sua máquina.\n"
        "- Modo nuvem: Turso (compatível com SQLite), sem perda de dados em reinícios.\n"
        "- O sistema alterna automaticamente entre os dois, dependendo das credenciais configuradas."
    )
