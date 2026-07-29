# -*- coding: utf-8 -*-
"""
app.py
======
Sistema de Gestão Financeira Pessoal e Familiar (com autenticação de usuário)
"""
from datetime import date, datetime
import io
import json

import pandas as pd
import plotly.express as px
import streamlit as st

import db
import utils

st.set_page_config(page_title="Gestão Financeira Familiar", page_icon="💰", layout="wide")

@st.cache_resource(show_spinner=False)
def _inicializar_banco_uma_vez():
    db.init_db()
    return True

_inicializar_banco_uma_vez()

FORMAS_PAGAMENTO = ["PIX", "Cartão de Crédito", "Cartão de Débito", "Dinheiro", "Transferência", "Financiamento"]
ORIGENS_RECEITA = ["Salário (Prefeitura de Maricá)", "Receitas (Paiva Projetos e Consultoria)", "Rendimentos (FIIs e Renda Fixa)", "Outros"]

HOJE = date.today()

def garantir_fixas_geradas(user, ano, mes):
    try:
        db.gerar_despesas_fixas_do_mes(ano, mes, requesting_user=user)
    except Exception:
        pass

def tabela_compras_df(lista):
    colunas = ["Descrição", "Categoria", "Cartão/Forma", "Data Compra", "Valor Total",
               "Valor Parcela", "Parcelas", "Restantes", "Valor Restante", "Situação"]
    if not lista:
        return pd.DataFrame(columns=colunas)
    linhas = []
    for p in lista:
        linhas.append({
            "Descrição": p["descricao"],
            "Categoria": p["categoria_nome"] or "—",
            "Cartão/Forma": p["cartao_nome"] or p["forma_pagamento"],
            "Data Compra": p["data_compra"],
            "Valor Total": utils.formatar_moeda(p["valor_total"]),
            "Valor Parcela": utils.formatar_moeda(p["valor_parcela"]),
            "Parcelas": f"{p['parcelas_pagas']}/{p['parcela_total']}",
            "Restantes": p["parcelas_restantes"],
            "Valor Restante": utils.formatar_moeda(p["valor_restante"]),
            "Situação": "✅ Quitada" if p["concluido"] else "🟡 Em andamento",
        })
    return pd.DataFrame(linhas, columns=colunas)

user = db.obter_ou_criar_usuario_padrao()

st.sidebar.title("💰 Finanças da Família")
pagina = st.sidebar.radio(
    "Navegação",
    [
        "📊 Dashboard",
        "📥 Receitas",
        "📤 Despesas",
        "🏷️ Categorias e Orçamento",
        "📁 Relatórios e Exportação",
        "⚙️ Configurações",
    ],
)

st.sidebar.markdown("---")
ano_sel = st.sidebar.selectbox("Ano de referência", list(range(HOJE.year - 3, HOJE.year + 2)), index=3)
mes_sel = st.sidebar.selectbox("Mês de referência", list(range(1, 13)), index=HOJE.month - 1, format_func=lambda m: utils.MESES_PT[m])
st.sidebar.caption("Esse período é usado no Dashboard, Relatórios e Orçamento.")

st.markdown(
    """
    <div style="background-color:#111111; color:#ffffff; padding:22px 28px; border-radius:10px; border:1px solid #2a2a2a; margin-bottom:18px;">
        <div style="font-size:26px; font-weight:700; letter-spacing:0.5px;">💰 Finanças da Família</div>
        <div style="font-size:14px; color:#bdbdbd; margin-top:4px;">Gestão financeira pessoal e familiar</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if pagina == "📊 Dashboard":
    st.title(f"📊 Dashboard — {utils.MESES_PT[mes_sel]}/{ano_sel}")
    garantir_fixas_geradas(user, ano_sel, mes_sel)

    receitas_list = db.list_receitas(user, ano=ano_sel, mes=mes_sel)
    despesas_list = db.list_despesas(user, ano=ano_sel, mes=mes_sel)

    total_receitas = sum(r.get("valor", 0) for r in receitas_list)
    total_despesas = sum(d.get("valor", 0) for d in despesas_list)
    percentual_reserva = db.get_reserva_percentual()
    valor_reserva = total_receitas * percentual_reserva / 100.0
    saldo_livre = total_receitas - total_despesas - valor_reserva

    resumo = {"total_receitas": total_receitas, "total_despesas": total_despesas, "percentual_reserva": percentual_reserva, "valor_reserva": valor_reserva, "saldo_livre": saldo_livre, "despesas": despesas_list}

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de Receitas", utils.formatar_moeda(resumo["total_receitas"]))
    col2.metric("Total de Despesas", utils.formatar_moeda(resumo["total_despesas"]))
    col3.metric(f"Reserva ({resumo['percentual_reserva']:.1f}%)", utils.formatar_moeda(resumo["valor_reserva"]))
    
    # O Delta começando com o sinal negativo "-" força o Streamlit a pintá-lo de vermelho
    delta_str = "- Atenção: negativo" if resumo["saldo_livre"] < 0 else None
    col4.metric("Saldo Livre Líquido", utils.formatar_moeda(resumo["saldo_livre"]), delta=delta_str)

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Distribuição de Despesas por Categoria")
        df_desp = utils.despesas_para_dataframe(resumo["despesas"])
        if not df_desp.empty:
            df_group = df_desp.groupby("categoria_nome", as_index=False)["valor"].sum()
            fig = px.pie(df_group, names="categoria_nome", values="valor", hole=0.4)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Nenhuma despesa lançada nesta competência.")

    with col_b:
        st.subheader("Evolução Mensal do Saldo")
        historico = []
        for i in range(11, -1, -1):
            d = db.add_months(date(ano_sel, mes_sel, 1), -i)
            garantir_fixas_geradas(user, d.year, d.month)
            r_receitas = db.list_receitas(user, ano=d.year, mes=d.month)
            r_despesas = db.list_despesas(user, ano=d.year, mes=d.month)
            total_r = sum(rr.get("valor", 0) for rr in r_receitas)
            total_d = sum(dd.get("valor", 0) for dd in r_despesas)
            perc = db.get_reserva_percentual()
            historico.append({"mes": f"{utils.MESES_PT[d.month][:3]}/{str(d.year)[2:]}", "Saldo Livre": total_r - total_d - (total_r * perc / 100.0), "Receitas": total_r, "Despesas": total_d})
        df_hist = pd.DataFrame(historico)
        fig2 = px.line(df_hist, x="mes", y=["Receitas", "Despesas", "Saldo Livre"], markers=True)
        fig2.update_layout(legend_title_text="", xaxis_title="", yaxis_title="R$")
        st.plotly_chart(fig2, width='stretch')

    st.markdown("---")
    st.subheader("🚦 Alertas de Teto de Gastos por Categoria")
    categorias = db.list_categorias(user)
    df_desp_cat = utils.despesas_para_dataframe(resumo["despesas"])
    algum_teto_definido = False

    for cat in categorias:
        if not cat.get("teto_mensal") or cat["teto_mensal"] <= 0: continue
        algum_teto_definido = True
        gasto = df_desp_cat.loc[df_desp_cat["categoria_nome"] == cat["nome"], "valor"].sum() if not df_desp_cat.empty else 0.0
        percentual = (gasto / cat["teto_mensal"]) * 100 if cat["teto_mensal"] else 0
        cor = utils.cor_status_teto(percentual)
        st.markdown(f"**{cat['nome']}** — {utils.formatar_moeda(gasto)} de {utils.formatar_moeda(cat['teto_mensal'])} ({percentual:.0f}%)")
        st.markdown(f'<div style="background-color:#e0e0e0; border-radius:6px; height:14px; width:100%;"><div style="background-color:{cor}; width:{min(percentual, 100)}%; height:14px; border-radius:6px;"></div></div>', unsafe_allow_html=True)
        if percentual >= 100: st.error(f"⚠️ Teto de **{cat['nome']}** ultrapassado!")
        elif percentual >= 80: st.warning(f"Atenção: **{cat['nome']}** já atingiu {percentual:.0f}% do teto.")
        st.write("")
    if not algum_teto_definido: st.info("Nenhum teto de gasto configurado ainda. Defina em '🏷️ Categorias e Orçamento'.")

    st.markdown("---")
    st.subheader("📋 Acompanhamento de Compras")
    st.caption("Tudo isso é preenchido automaticamente a partir do que você registra em '📤 Despesas' — não precisa cadastrar de novo aqui.")
    tab_vista, tab_parcelado, tab_financ = st.tabs(["💳 À Vista no Cartão", "📦 Parcelado no Cartão", "🏦 Financiamentos"])
    with tab_vista:
        lista_vista = db.list_compras_por_tipo(user, forma_pagamento="Cartão de Crédito", somente_parceladas=False)
        st.dataframe(tabela_compras_df(lista_vista), width='stretch', hide_index=True)
    with tab_parcelado:
        lista_parcelado = db.list_compras_por_tipo(user, forma_pagamento="Cartão de Crédito", somente_parceladas=True)
        st.dataframe(tabela_compras_df(lista_parcelado), width='stretch', hide_index=True)
    with tab_financ:
        lista_financ = db.list_compras_por_tipo(user, forma_pagamento="Financiamento")
        st.dataframe(tabela_compras_df(lista_financ), width='stretch', hide_index=True)

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
            if valor <= 0: st.error("Informe um valor maior que zero.")
            else:
                try:
                    db.add_receita(data_receita.isoformat(), origem, valor, observacao, user_id=user.get("id"))
                    perc = db.get_reserva_percentual()
                    st.success(f"Receita registrada! Reserva automática ({perc:.1f}%): {utils.formatar_moeda(valor * perc / 100)}")
                except Exception as e: st.error(f"Não foi possível registrar a receita: {e}")

    st.markdown("---")
    st.subheader(f"Receitas de {utils.MESES_PT[mes_sel]}/{ano_sel}")
    receitas = db.list_receitas(user, ano_sel, mes_sel)
    df = utils.receitas_para_dataframe(receitas)
    if df.empty: st.info("Nenhuma receita lançada neste período.")
    else:
        df_show = df.copy()
        df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
        st.dataframe(df_show, width='stretch', hide_index=True)
        id_excluir = st.selectbox("Excluir lançamento (selecione o ID)", [None] + df["id"].tolist())
        if id_excluir and st.button("🗑️ Excluir receita selecionada"):
            try:
                db.delete_receita(id_excluir, user)
                st.success("Receita excluída.")
                st.rerun()
            except PermissionError as e: st.error(str(e))

elif pagina == "📤 Despesas":
    st.title("📤 Despesas (Saídas)")
    st.caption("Tudo o que você lançar aqui — seja uma despesa avulsa, uma despesa fixa gerada automaticamente ou uma compra no cartão — soma no mesmo total de despesas do Dashboard e dos Relatórios. Nada disso muda entre as abas abaixo.")

    tab_lancar, tab_fixas, tab_cartoes = st.tabs(["📝 Lançar Despesa", "🔁 Despesas Fixas", "💳 Cartões"])

    with tab_lancar:
        categorias = db.list_categorias(user)
        cartoes = db.list_cartoes(user)
        nomes_categorias = {c["nome"]: c["id"] for c in categorias}

        def _rotulo_cartao(c):
            selo = utils.BANCOS_EMOJI.get(c.get("banco"), "") if c.get("banco") else ""
            return f"{selo} — {c['nome']}" if selo else c["nome"]
        nomes_cartoes = {_rotulo_cartao(c): c["id"] for c in cartoes}

        with st.form("form_despesa", clear_on_submit=True):
            c1, c2 = st.columns(2)
            data_compra = c1.date_input("Data da compra/despesa", value=HOJE)
            descricao = c2.text_input("Descrição")

            c3, c4 = st.columns(2)
            categoria_nome = c3.selectbox("Categoria", list(nomes_categorias.keys()))
            forma_pagamento = c4.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO)

            cartao_nome = None
            if forma_pagamento in ("Cartão de Crédito", "Cartão de Débito"):
                if nomes_cartoes: cartao_nome = st.selectbox("Cartão utilizado", list(nomes_cartoes.keys()))
                else: st.warning("Nenhum cartão cadastrado. Cadastre na aba '💳 Cartões' aqui ao lado.")

            c5, c6 = st.columns(2)
            valor_total = c5.number_input("Valor total (R$)", min_value=0.0, step=10.0, format="%.2f")
            
            parcelas = 1
            data_vencimento = data_compra
            
            if forma_pagamento in ("Cartão de Crédito", "Financiamento"):
                max_parcelas = 48 if forma_pagamento == "Cartão de Crédito" else 420
                parcelas = c6.number_input("Quantidade de parcelas", min_value=1, max_value=max_parcelas, value=1, step=1)
                
                st.markdown("👇 **Data do Vencimento**")
                data_vencimento = st.date_input("Informe a data de vencimento da 1ª parcela", value=data_compra)

            enviado = st.form_submit_button("➕ Registrar Despesa")

            if enviado:
                if valor_total <= 0: st.error("Informe um valor maior que zero.")
                elif not descricao.strip(): st.error("Informe uma descrição.")
                else:
                    try:
                        categoria_id = nomes_categorias.get(categoria_nome)
                        cartao_id = nomes_cartoes.get(cartao_nome) if cartao_nome else None
                        
                        db.add_despesa(data_compra, categoria_id, descricao, valor_total,
                                        forma_pagamento, cartao_id, parcelas, 
                                        primeira_competencia=data_vencimento, user_id=user.get("id"))

                        if parcelas > 1:
                            st.success(f"Despesa parcelada em {parcelas}x registrada! 1ª parcela com vencimento em {data_vencimento.strftime('%d/%m/%Y')}.")
                        else:
                            st.success("Despesa registrada com sucesso!")
                    except Exception as e:
                        st.error(f"Não foi possível registrar a despesa: {e}")

        st.markdown("---")
        st.subheader(f"Despesas — competência de {utils.MESES_PT[mes_sel]}/{ano_sel}")
        garantir_fixas_geradas(user, ano_sel, mes_sel)
        despesas = db.list_despesas(user, ano_sel, mes_sel)
        df = utils.despesas_para_dataframe(despesas)
        
        if df.empty: 
            st.info("Nenhuma despesa nesta competência.")
        else:
            df_show = df.copy()
            df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
            df_show["parcela"] = df_show["parcela_atual"].astype(str) + "/" + df_show["parcela_total"].astype(str)
            
            # Aqui mostramos a data_competencia (Vencimento) na tabela para centralizar melhor a informação de quando ela debita
            df_show = df_show[["id", "data_competencia", "categoria_nome", "descricao", "valor", "forma_pagamento", "cartao_nome", "parcela"]]
            df_show.columns = ["ID", "Vencimento", "Categoria", "Descrição", "Valor", "Pagamento", "Cartão", "Parcela"]
            st.dataframe(df_show, width='stretch', hide_index=True)

            st.markdown("---")
            st.subheader("✏️ Editar ou 🗑️ Excluir Lançamento")
            st.caption("Selecione o ID na lista acima para modificar ou excluir qualquer informação da parcela (como valor ou vencimento).")
            
            id_acao = st.selectbox("Selecione o ID da despesa:", [None] + df["id"].tolist())
            
            if id_acao:
                desp_edit = next((d for d in despesas if d["id"] == id_acao), None)
                if desp_edit:
                    with st.expander("📝 Modificar lançamento selecionado", expanded=True):
                        with st.form("form_edit_despesa"):
                            e_c1, e_c2 = st.columns(2)
                            edit_data_compra = e_c1.date_input("Data da Compra", value=datetime.strptime(desp_edit["data_compra"], "%Y-%m-%d").date())
                            edit_data_venc = e_c2.date_input("Data de Vencimento", value=datetime.strptime(desp_edit["data_competencia"], "%Y-%m-%d").date())
                            
                            edit_desc = st.text_input("Descrição", value=desp_edit["descricao"])
                            
                            e_c3, e_c4 = st.columns(2)
                            idx_cat = list(nomes_categorias.values()).index(desp_edit["categoria_id"]) if desp_edit["categoria_id"] in nomes_categorias.values() else 0
                            edit_cat = e_c3.selectbox("Categoria", list(nomes_categorias.keys()), index=idx_cat)
                            
                            idx_forma = FORMAS_PAGAMENTO.index(desp_edit["forma_pagamento"]) if desp_edit["forma_pagamento"] in FORMAS_PAGAMENTO else 0
                            edit_forma = e_c4.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, index=idx_forma)
                            
                            edit_cartao_nome = None
                            if edit_forma in ("Cartão de Crédito", "Cartão de Débito"):
                                idx_cartao = 0
                                if desp_edit["cartao_id"] and desp_edit["cartao_id"] in nomes_cartoes.values():
                                    idx_cartao = list(nomes_cartoes.values()).index(desp_edit["cartao_id"])
                                if nomes_cartoes:
                                    edit_cartao_nome = st.selectbox("Cartão", list(nomes_cartoes.keys()), index=idx_cartao)
                                else:
                                    st.warning("Nenhum cartão cadastrado.")
                                    
                            edit_valor = st.number_input("Valor da Parcela (R$)", min_value=0.0, step=10.0, format="%.2f", value=float(desp_edit["valor"]))
                            
                            salvar_edicao = st.form_submit_button("💾 Salvar Alterações")
                            
                            if salvar_edicao:
                                try:
                                    novo_cat_id = nomes_categorias.get(edit_cat)
                                    novo_cartao_id = nomes_cartoes.get(edit_cartao_nome) if edit_cartao_nome else None
                                    db.edit_despesa(id_acao, edit_data_compra.isoformat(), edit_data_venc.isoformat(), novo_cat_id, edit_desc, edit_valor, edit_forma, novo_cartao_id, user)
                                    st.success("Lançamento atualizado com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao editar: {e}")
                                    
                        st.markdown("**Ações de Exclusão:**")
                        col_del1, col_del2 = st.columns(2)
                        if col_del1.button("🗑️ Excluir apenas esta parcela"):
                            try:
                                db.delete_despesa(id_acao, user)
                                st.success("Parcela excluída.")
                                st.rerun()
                            except PermissionError as e: st.error(str(e))
                        
                        if desp_edit["parcela_total"] > 1:
                            if col_del2.button("🗑️ Excluir TODAS as parcelas desta compra"):
                                try:
                                    db.delete_grupo(desp_edit["compra_grupo"], user)
                                    st.success("Todas as parcelas da compra foram excluídas.")
                                    st.rerun()
                                except PermissionError as e: st.error(str(e))

    with tab_fixas:
        st.caption("Ex.: Aluguel, Internet, Assinaturas. Gere os lançamentos do mês com um clique.")
        categorias = db.list_categorias(user)
        cartoes = db.list_cartoes(user)
        nomes_categorias = {c["nome"]: c["id"] for c in categorias}
        def _rotulo_cartao_fixa(c):
            selo = utils.BANCOS_EMOJI.get(c.get("banco"), "") if c.get("banco") else ""
            return f"{selo} — {c['nome']}" if selo else c["nome"]
        nomes_cartoes = {_rotulo_cartao_fixa(c): c["id"] for c in cartoes}

        with st.form("form_fixa", clear_on_submit=True):
            c1, c2 = st.columns(2)
            descricao = c1.text_input("Descrição (ex: Aluguel)")
            categoria_nome = c2.selectbox("Categoria", list(nomes_categorias.keys()))
            c3, c4, c5 = st.columns(3)
            valor = c3.number_input("Valor mensal (R$)", min_value=0.0, step=10.0, format="%.2f")
            forma_pagamento = c4.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO)
            dia_vencimento = c5.number_input("Dia de vencimento", min_value=1, max_value=28, value=5)
            cartao_nome = None
            if forma_pagamento in ("Cartão de Crédito", "Cartão de Débito") and nomes_cartoes: cartao_nome = st.selectbox("Cartão", list(nomes_cartoes.keys()))

            enviado = st.form_submit_button("➕ Cadastrar Despesa Fixa")
            if enviado:
                if not descricao.strip() or valor <= 0: st.error("Preencha descrição e valor corretamente.")
                else:
                    try:
                        cartao_id = nomes_cartoes.get(cartao_nome) if cartao_nome else None
                        db.add_despesa_fixa(descricao, nomes_categorias[categoria_nome], valor, forma_pagamento, cartao_id, dia_vencimento, user_id=user.get("id"))
                        st.success("Despesa fixa cadastrada!")
                    except Exception as e: st.error(f"Não foi possível cadastrar a despesa fixa: {e}")

        st.markdown("---")
        st.subheader("Despesas fixas cadastradas")
        fixas = db.list_despesas_fixas(user, somente_ativas=False)
        if not fixas: st.info("Nenhuma despesa fixa cadastrada.")
        else:
            df_fixas = pd.DataFrame([dict(f) for f in fixas])
            df_show = df_fixas[["id", "descricao", "categoria_nome", "valor", "forma_pagamento", "dia_vencimento", "ativa"]].copy()
            df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
            df_show["ativa"] = df_show["ativa"].apply(lambda x: "✅ Ativa" if x else "⏸️ Pausada")
            df_show.columns = ["ID", "Descrição", "Categoria", "Valor", "Pagamento", "Dia Venc.", "Status"]
            st.dataframe(df_show, width='stretch', hide_index=True)

            col1, col2, col3 = st.columns(3)
            id_alvo = col1.selectbox("Selecionar ID para ação", df_fixas["id"].tolist())
            if col2.button("⏸️ Pausar / ▶️ Reativar"):
                try:
                    atual = df_fixas.loc[df_fixas["id"] == id_alvo, "ativa"].values[0]
                    db.set_despesa_fixa_ativa(id_alvo, not atual, user)
                    st.rerun()
                except PermissionError as e: st.error(str(e))
            if col3.button("🗑️ Excluir cadastro"):
                try:
                    db.delete_despesa_fixa(id_alvo, user)
                    st.rerun()
                except PermissionError as e: st.error(str(e))

        st.markdown("---")
        st.subheader(f"Lançamentos do mês selecionado ({utils.MESES_PT[mes_sel]}/{ano_sel})")
        if st.button("🔁 Atualizar lançamentos agora"):
            qtd = db.gerar_despesas_fixas_do_mes(ano_sel, mes_sel, requesting_user=user)
            if qtd > 0: st.success(f"{qtd} lançamento(s) gerado(s).")
            else: st.info("Todos os lançamentos deste mês já haviam sido gerados anteriormente.")

    with tab_cartoes:
        st.caption("O selo abaixo (emoji colorido) é apenas uma identificação visual — não reproduz a logomarca oficial de nenhum banco, já que são marcas registradas.")
        with st.form("form_cartao", clear_on_submit=True):
            c1, c2 = st.columns(2)
            banco = c1.selectbox("Banco / Instituição", list(utils.BANCOS_EMOJI.keys()), format_func=lambda b: utils.BANCOS_EMOJI[b])
            nome = c2.text_input("Apelido do cartão (ex: Nubank Roxinho, Itaú Platinum)")
            c3, c4 = st.columns(2)
            dia_fechamento = c3.number_input("Dia de fechamento da fatura", min_value=1, max_value=28, value=25)
            dia_vencimento = c4.number_input("Dia de vencimento da fatura", min_value=1, max_value=28, value=5)
            enviado = st.form_submit_button("➕ Cadastrar Cartão")
            if enviado:
                if not nome.strip(): st.error("Informe o apelido do cartão.")
                else:
                    try:
                        db.add_cartao(nome, dia_fechamento, dia_vencimento, banco=banco, user_id=user.get("id"))
                        st.success(f"Cartão {utils.BANCOS_EMOJI[banco]} cadastrado!")
                    except Exception: st.error("Já existe um cartão com esse nome.")

        st.markdown("---")
        cartoes_cad = db.list_cartoes(user)
        if not cartoes_cad: st.info("Nenhum cartão cadastrado ainda.")
        else:
            df = utils.cartoes_para_dataframe(cartoes_cad)
            df_show = df.copy()
            df_show["banco"] = df_show["banco"].apply(lambda b: utils.BANCOS_EMOJI.get(b, b or "—"))
            df_show.columns = ["ID", "Banco", "Nome", "Dia Fechamento", "Dia Vencimento"]
            st.dataframe(df_show, width='stretch', hide_index=True)
            id_excluir = st.selectbox("Excluir cartão (ID)", [None] + [c["id"] for c in cartoes_cad])
            if id_excluir and st.button("🗑️ Excluir cartão"):
                try:
                    db.delete_cartao(id_excluir, user)
                    st.rerun()
                except (PermissionError, db.RegistroVinculadoError) as e: st.error(str(e))
            st.info("📌 **Regra de fechamento:** compras feitas *após* o dia de fechamento têm a 1ª parcela lançada automaticamente na fatura (competência) do **mês seguinte**.")

        st.markdown("---")
        st.subheader("🧾 Parcelamentos em Andamento")
        parcelamentos = db.list_parcelamentos(user)
        if not parcelamentos: st.info("Nenhuma compra parcelada no cartão até o momento.")
        else:
            for p in parcelamentos:
                titulo = f"{p['descricao']} — {p['cartao_nome'] or 'sem cartão'}"
                if p["concluido"]: titulo += " ✅ (quitada)"
                with st.container(border=True):
                    st.markdown(f"**{titulo}**")
                    colx, coly, colz, colw = st.columns(4)
                    colx.metric("Valor total da compra", utils.formatar_moeda(p["valor_total"]))
                    coly.metric("Valor da parcela", utils.formatar_moeda(p["valor_parcela"]))
                    colz.metric("Parcelas pagas", f"{p['parcelas_pagas']} / {p['parcela_total']}")
                    colw.metric("Parcelas restantes", p["parcelas_restantes"])
                    progresso = p["parcelas_pagas"] / p["parcela_total"] if p["parcela_total"] else 0
                    st.progress(min(max(progresso, 0.0), 1.0))
                    if not p["concluido"]: st.caption(f"Faltam {utils.formatar_moeda(p['valor_restante'])} para quitar essa compra ({p['parcelas_restantes']} parcela(s) de {utils.formatar_moeda(p['valor_parcela'])}).")
                    else: st.caption("Compra totalmente quitada. 🎉")

elif pagina == "🏷️ Categorias e Orçamento":
    st.title("🏷️ Categorias de Despesa e Teto de Gastos")
    with st.form("form_categoria", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nova categoria (ex: Pet, Viagem)")
        teto = c2.number_input("Teto mensal (R$) — opcional, 0 = sem limite", min_value=0.0, step=50.0)
        enviado = st.form_submit_button("➕ Adicionar Categoria")
        if enviado:
            if not nome.strip(): st.error("Informe o nome da categoria.")
            else:
                try:
                    db.add_categoria(nome, teto, user_id=user.get("id"))
                    st.success("Categoria criada!")
                except Exception: st.error("Já existe uma categoria com esse nome.")

    st.markdown("---")
    st.subheader("Categorias cadastradas — defina/edite o teto mensal")
    categorias = db.list_categorias(user)
    for cat in categorias:
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.write(f"**{cat['nome']}**")
        novo_teto = col2.number_input(f"Teto (R$) — {cat['nome']}", min_value=0.0, value=float(cat.get("teto_mensal") or 0), step=50.0, key=f"teto_{cat['id']}", label_visibility="collapsed")
        if col3.button("Salvar", key=f"salvar_{cat['id']}"):
            try:
                db.update_categoria_teto(cat["id"], novo_teto, requesting_user=user)
                st.success(f"Teto de {cat['nome']} atualizado!")
                st.rerun()
            except PermissionError as e: st.error(str(e))

    st.markdown("---")
    id_excluir = st.selectbox("Excluir categoria (ID)", [None] + [c["id"] for c in categorias])
    if id_excluir and st.button("🗑️ Excluir categoria selecionada"):
        try:
            db.delete_categoria(id_excluir, requesting_user=user)
            st.rerun()
        except (PermissionError, db.RegistroVinculadoError) as e: st.error(str(e))

elif pagina == "📁 Relatórios e Exportação":
    st.title("📁 Relatórios, Filtros e Exportação")
    modo = st.radio("Visualizar por período:", ["Mensal", "Diário (dentro do mês)", "Anual"], horizontal=True)

    if modo == "Anual":
        for m in range(1, 13): garantir_fixas_geradas(user, ano_sel, m)
        receitas = db.list_receitas(user, ano_sel, None)
        despesas = db.list_despesas(user, ano_sel, None)
    else:
        garantir_fixas_geradas(user, ano_sel, mes_sel)
        receitas = db.list_receitas(user, ano_sel, mes_sel)
        despesas = db.list_despesas(user, ano_sel, mes_sel)

    df_r = utils.receitas_para_dataframe(receitas)
    df_d = utils.despesas_para_dataframe(despesas)

    if modo == "Diário (dentro do mês)" and not df_d.empty:
        dia_filtro = st.date_input("Selecione um dia específico (opcional)", value=None)
        if dia_filtro:
            df_d = df_d[df_d["data_compra"] == dia_filtro.isoformat()]
            df_r = df_r[df_r["data"] == dia_filtro.isoformat()] if not df_r.empty else df_r

    st.subheader("📥 Receitas")
    st.dataframe(df_r, width='stretch', hide_index=True)
    st.subheader("📤 Despesas")
    st.dataframe(df_d, width='stretch', hide_index=True)

    st.markdown("---")
    st.subheader("⬇️ Exportar dados")
    col1, col2 = st.columns(2)
    with col1:
        csv_buffer = io.StringIO()
        df_export = pd.concat([df_r.assign(tipo="Receita"), df_d.rename(columns={"data_compra": "data"}).assign(tipo="Despesa")], ignore_index=True, sort=False)
        df_export.to_csv(csv_buffer, index=False, sep=";", decimal=",")
        st.download_button("📄 Baixar CSV", data=csv_buffer.getvalue(), file_name=f"financas_{ano_sel}_{mes_sel if modo != 'Anual' else 'ANO'}.csv", mime="text/csv")
    with col2:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df_r.to_excel(writer, sheet_name="Receitas", index=False)
            df_d.to_excel(writer, sheet_name="Despesas", index=False)
        st.download_button("📊 Baixar Excel", data=excel_buffer.getvalue(), file_name=f"financas_{ano_sel}_{mes_sel if modo != 'Anual' else 'ANO'}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif pagina == "⚙️ Configurações":
    st.title("⚙️ Configurações Gerais")
    st.subheader("🐷 Meta de Reserva / Investimentos")
    percentual_atual = db.get_reserva_percentual()
    novo_percentual = st.slider("Percentual de todas as receitas do mês a ser destinado automaticamente à reserva:", min_value=0.0, max_value=100.0, value=float(percentual_atual), step=1.0)
    if st.button("💾 Salvar percentual de reserva"):
        db.set_reserva_percentual(novo_percentual)
        st.success(f"Reserva automática configurada para {novo_percentual:.1f}% das receitas.")

    st.markdown("---")
    st.subheader("🗄️ Status do Banco de Dados")
    if db.usando_banco_em_nuvem(): st.success(db.get_backend_info())
    else: st.info(db.get_backend_info())
    if st.button("💾 Fazer backup local agora"):
        try:
            path = db.backup_db()
            if path: st.success(f"Backup criado: {path}")
            else: st.warning("Backup não disponível para backend em nuvem.")
        except Exception as e: st.error("Erro ao criar backup: " + str(e))

    with st.expander("🔧 Diagnóstico e reparo do banco de dados"):
        if st.button("🔍 Verificar agora"):
            try:
                tabelas = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                st.write("**Tabelas existentes:**", [t["name"] for t in tabelas])
                migracoes = db.fetch_all("SELECT nome, executado_em FROM migracoes_executadas ORDER BY nome")
                st.write("**Migrações concluídas:**", {m["nome"]: m["executado_em"] for m in migracoes} or "nenhuma")
                for tabela, coluna in (("categorias", "nome"), ("cartoes", "nome"), ("despesas_fixas", "descricao")):
                    tem_unique = db._tabela_tem_unique_em_coluna(tabela, coluna)
                    total = db.fetch_one(f"SELECT COUNT(*) AS n FROM {tabela}")["n"]
                    residuos = [nome for nome in (f"{tabela}_migracao_old", f"{tabela}__nova_sem_unique") if db._tabela_existe(nome)]
                    if tem_unique or residuos: st.error(f"⚠️ **{tabela}.{coluna}**: {total} linha(s). UNIQUE: {tem_unique}. Resíduos: {residuos or 'nenhum'}.")
                    else: st.success(f"✅ **{tabela}.{coluna}**: {total} linha(s). Ok.")
            except Exception as e: st.error(f"Erro ao verificar: {e}")
        if st.button("🛠️ Forçar correção agora"):
            try:
                db._migrar_categorias_remover_unique_global(reconciliar_residuos=True)
                db._migrar_cartoes_remover_unique_global(reconciliar_residuos=True)
                db._migrar_despesas_fixas_remover_unique_global(reconciliar_residuos=True)
                db.execute("INSERT OR IGNORE INTO migracoes_executadas (nome) VALUES (?), (?), (?)", ("remover_unique_categorias", "remover_unique_cartoes", "remover_unique_despesas_fixas"))
                st.success("Correção executada.")
            except Exception as e: st.error(f"Erro ao corrigir: {e}")

    st.markdown("---")
    st.subheader("ℹ️ Sobre o sistema")
    st.write("Sistema de Gestão Financeira Pessoal e Familiar — versão 1.2\n\n- Modo local: SQLite (`financas.db`) na sua máquina.\n- Modo nuvem: Turso (compatível com SQLite), sem perda de dados em reinícios.\n- O sistema alterna automaticamente entre os dois, dependendo das credenciais configuradas.")

def json_safe(s):
    if not s: return None
    try: return json.loads(s)
    except Exception: return s

if pagina == "⚙️ Configurações":
    st.markdown("---")
    st.header("🗂️ Histórico de Alterações")
    logs = db.get_audit_logs(limit=200)
    st.write(f"Mostrando {len(logs)} registro(s) de auditoria")
    for L in logs:
        with st.expander(f"{L.get('timestamp')} — {L.get('action')} — {L.get('table_name')}"):
            st.write("row_id:", L.get("row_id"))
            st.write("antes:", json_safe(L.get("before_json")))
            st.write("depois:", json_safe(L.get("after_json")))
