# -*- coding: utf-8 -*-
"""
app.py
======
Sistema de Gestão Financeira Pessoal e Familiar (com autenticação de usuário)
"""
from datetime import date, datetime
import calendar
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

OPCOES_CAIXA = ["PF (Pessoal)", "PJ (Paiva Projetos e Consultoria)"]
OPCOES_RESPONSAVEL = ["Conjunto", "Felipe", "Esposa"]

HOJE = date.today()

# --- CSS GLOBAL: TRANSFORMA O MENU LATERAL EM BOTÕES FLUTUANTES ---
st.markdown("""
    <style>
    div[data-testid="stSidebar"] div.stRadio > div[role="radiogroup"] {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    div[data-testid="stSidebar"] div.stRadio > div[role="radiogroup"] > label {
        background-color: #1E212B;
        border: 1px solid #00FFAA;
        border-radius: 8px;
        padding: 10px 15px;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
    div[data-testid="stSidebar"] div.stRadio > div[role="radiogroup"] > label:hover {
        background-color: #00FFAA;
        transform: scale(1.03);
    }
    div[data-testid="stSidebar"] div.stRadio > div[role="radiogroup"] > label:hover p {
        color: #1E212B !important;
        font-weight: 800;
    }
    div[data-testid="stSidebar"] div.stRadio > div[role="radiogroup"] > label span[data-baseweb="radio"] {
        display: none;
    }
    </style>
""", unsafe_allow_html=True)

def garantir_fixas_geradas(user, ano, mes):
    try:
        db.gerar_despesas_fixas_do_mes(ano, mes, requesting_user=user)
    except Exception:
        pass

def tabela_compras_df(lista):
    colunas = ["Caixa", "Descrição", "Categoria", "Cartão/Forma", "Data Compra", "Valor Total",
               "Valor Parcela", "Parcelas", "Restantes", "Valor Restante", "Situação"]
    if not lista:
        return pd.DataFrame(columns=colunas)
    linhas = []
    for p in lista:
        linhas.append({
            "Caixa": p.get("caixa") or "PF (Pessoal)",
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
    <div style="background-color:#1E212B; color:#ffffff; padding:22px 28px; border-radius:10px; border:1px solid #00FFAA; margin-bottom:18px;">
        <div style="font-size:26px; font-weight:700; letter-spacing:0.5px;">💰 Inteligência Financeira</div>
        <div style="font-size:14px; color:#bdbdbd; margin-top:4px;">Painel de Controle e Fluxo de Caixa ERP</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if pagina == "📊 Dashboard":
    
    # --- MENU FLUTUANTE DE ATALHOS PARA O DASHBOARD ---
    st.markdown("""
        <style>
        .floating-menu {
            position: fixed;
            bottom: 30px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .fab-button {
            background-color: #1E212B;
            color: #00FFAA !important;
            border: 1px solid #00FFAA;
            border-radius: 20px;
            padding: 8px 15px;
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            text-align: right;
            box-shadow: 0 4px 10px rgba(0,0,0,0.5);
            transition: all 0.2s ease-in-out;
            opacity: 0.6;
        }
        .fab-button:hover {
            background-color: #00FFAA;
            color: #1E212B !important;
            transform: scale(1.05);
            opacity: 1;
        }
        </style>
        <div class="floating-menu">
            <a href="#ancora-kpis" class="fab-button">📊 Resumo Geral</a>
            <a href="#ancora-proventos" class="fab-button">📈 Rendimentos</a>
            <a href="#ancora-graficos" class="fab-button">📉 Gráficos</a>
            <a href="#ancora-alertas" class="fab-button">🚦 Alertas</a>
            <a href="#ancora-projeto18" class="fab-button">🚀 Projeto 18</a>
            <a href="#ancora-compras" class="fab-button">💳 Compras</a>
            <a href="#ancora-edicao" class="fab-button">✏️ Editar</a>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<div id='ancora-kpis'></div>", unsafe_allow_html=True)
    st.title(f"📊 Dashboard — {utils.MESES_PT[mes_sel]}/{ano_sel}")
    garantir_fixas_geradas(user, ano_sel, mes_sel)

    # Chave Seletora Global de Caixa
    st.write("**Visão Estratégica de Caixa:**")
    filtro_caixa = st.radio("Selecione o fluxo que deseja analisar:", ["Consolidado", "PF (Pessoal)", "PJ (Paiva Projetos e Consultoria)"], horizontal=True, label_visibility="collapsed")

    receitas_raw = db.list_receitas(user, ano=ano_sel, mes=mes_sel)
    despesas_raw = db.list_despesas(user, ano=ano_sel, mes=mes_sel)

    if filtro_caixa != "Consolidado":
        receitas_list = [r for r in receitas_raw if r.get('caixa') == filtro_caixa or (filtro_caixa == "PF (Pessoal)" and not r.get('caixa'))]
        despesas_list = [d for d in despesas_raw if d.get('caixa') == filtro_caixa or (filtro_caixa == "PF (Pessoal)" and not d.get('caixa'))]
    else:
        receitas_list = receitas_raw
        despesas_list = despesas_raw

    total_receitas = sum(r.get("valor", 0) for r in receitas_list)
    total_despesas = sum(d.get("valor", 0) for d in despesas_list)
    percentual_reserva = db.get_reserva_percentual()
    valor_reserva = total_receitas * percentual_reserva / 100.0
    saldo_livre = total_receitas - total_despesas - valor_reserva

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de Receitas", utils.formatar_moeda(total_receitas))
    col2.metric("Total de Despesas", utils.formatar_moeda(total_despesas))
    col3.metric(f"Reserva ({percentual_reserva:.1f}%)", utils.formatar_moeda(valor_reserva))
    delta_str = "- Atenção: negativo" if saldo_livre < 0 else "Saldo Saudável"
    col4.metric("Saldo Livre Líquido", utils.formatar_moeda(saldo_livre), delta=delta_str)

    if st.button("🎉 Consolidar Resultado do Mês"):
        if saldo_livre >= 0:
            st.balloons()
            st.success("Excelente! Você fechou o mês no azul e dentro do planejamento.")
        else:
            st.warning("O mês fechou negativo. Revise a seção de alertas de teto de gastos abaixo.")

    st.markdown("---")
    st.markdown("<div id='ancora-proventos'></div>", unsafe_allow_html=True)
    st.subheader("📈 Proventos e Renda Passiva (BTG Pactual / FIIs)")
    st.caption("Evolução dos rendimentos que trabalham por você isolados do seu fluxo de caixa principal.")
    df_rec = utils.receitas_para_dataframe(receitas_list)
    if not df_rec.empty:
        df_rend = df_rec[df_rec['origem'].str.contains('Rendimentos', case=False, na=False)]
        if not df_rend.empty:
            fig_rend = px.bar(df_rend, x='data', y='valor', text='valor', title="", color_discrete_sequence=['#00FFAA'])
            fig_rend.update_traces(texttemplate='R$ %{text:.2f}', textposition='outside')
            fig_rend.update_layout(xaxis_title="", yaxis_title="Rendimento Diário", margin=dict(t=10, b=0, l=0, r=0))
            st.plotly_chart(fig_rend, width='stretch')
        else:
            st.info("Nenhum rendimento de FIIs ou Renda Fixa lançado neste mês.")
    else:
        st.info("Nenhum rendimento de FIIs ou Renda Fixa lançado neste mês.")

    st.markdown("---")
    st.markdown("<div id='ancora-graficos'></div>", unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Distribuição por Categoria")
        df_desp = utils.despesas_para_dataframe(despesas_list)
        if not df_desp.empty:
            df_group = df_desp.groupby("categoria_nome", as_index=False)["valor"].sum()
            fig = px.pie(df_group, names="categoria_nome", values="valor", hole=0.5, color_discrete_sequence=px.colors.sequential.Tealgrn)
            fig.update_layout(margin=dict(t=10, b=0, l=0, r=0))
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Nenhuma despesa lançada neste filtro.")

    with col_b:
        st.subheader("Divisão por Responsável")
        if not df_desp.empty:
            df_resp = df_desp.copy()
            df_resp['responsavel'] = df_resp['responsavel'].fillna('Conjunto')
            df_group_resp = df_resp.groupby("responsavel", as_index=False)["valor"].sum()
            fig_resp = px.pie(df_group_resp, names="responsavel", values="valor", hole=0.5, color_discrete_sequence=['#00FFAA', '#1E90FF', '#FF00AA'])
            fig_resp.update_layout(margin=dict(t=10, b=0, l=0, r=0))
            st.plotly_chart(fig_resp, width='stretch')
        else:
            st.info("Sem dados de responsáveis neste filtro.")

    st.markdown("---")
    st.markdown("<div id='ancora-alertas'></div>", unsafe_allow_html=True)
    st.subheader("🚦 Alertas Preditivos de Teto de Gastos")
    
    dias_no_mes = calendar.monthrange(ano_sel, mes_sel)[1]
    dia_atual = HOJE.day if (ano_sel == HOJE.year and mes_sel == HOJE.month) else dias_no_mes
    progresso_tempo = dia_atual / dias_no_mes

    categorias = db.list_categorias(user)
    algum_teto_definido = False

    for cat in categorias:
        if not cat.get("teto_mensal") or cat["teto_mensal"] <= 0: continue
        algum_teto_definido = True
        gasto = df_desp.loc[df_desp["categoria_nome"] == cat["nome"], "valor"].sum() if not df_desp.empty else 0.0
        percentual = (gasto / cat["teto_mensal"]) * 100 if cat["teto_mensal"] else 0
        cor = utils.cor_status_teto(percentual)
        
        st.markdown(f"**{cat['nome']}** — {utils.formatar_moeda(gasto)} de {utils.formatar_moeda(cat['teto_mensal'])} ({percentual:.0f}%)")
        st.markdown(f'<div style="background-color:#262730; border-radius:6px; height:14px; width:100%;"><div style="background-color:{cor}; width:{min(percentual, 100)}%; height:14px; border-radius:6px;"></div></div>', unsafe_allow_html=True)
        
        if percentual >= 100: 
            st.error(f"⚠️ Teto estourado para a categoria **{cat['nome']}**.")
        elif (percentual / 100) > (progresso_tempo * 1.25): 
            st.warning(f"Atenção: Ritmo acelerado! Você já consumiu {percentual:.0f}% do teto, mas o mês está apenas {progresso_tempo*100:.0f}% concluído. Segure os gastos.")
        elif percentual >= 80: 
            st.info(f"Fique de olho: Você está próximo de bater o limite para **{cat['nome']}**.")
        st.write("")
        
    if not algum_teto_definido: st.info("Nenhum teto de gasto configurado ainda. Defina em '🏷️ Categorias e Orçamento'.")

    st.markdown("---")
    st.markdown("<div id='ancora-projeto18'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("🚀 Fundo de Emancipação (Projeto 18 Anos)")
        st.caption("Visão gamificada e de longo prazo: projete o efeito multiplicador dos juros compostos para o futuro da sua família.")
        
        c_sim1, c_sim2, c_sim3 = st.columns(3)
        aporte_mensal = c_sim1.number_input("Aporte Mensal Simulado (R$)", value=500.0, step=50.0)
        taxa_anual = c_sim2.number_input("Taxa de Juros Anual Esperada (%)", value=11.5, step=0.5)
        anos_horizonte = c_sim3.number_input("Horizonte (Anos)", value=18, step=1)
        
        if anos_horizonte > 0:
            taxa_mensal = (1 + (taxa_anual / 100)) ** (1/12) - 1
            meses_totais = int(anos_horizonte * 12)
            montante_final = aporte_mensal * (((1 + taxa_mensal) ** meses_totais - 1) / taxa_mensal) if taxa_mensal > 0 else aporte_mensal * meses_totais
            juros_acumulados = montante_final - (aporte_mensal * meses_totais)
            
            c_res1, c_res2 = st.columns(2)
            c_res1.metric(f"Patrimônio Estimado em {anos_horizonte} anos", utils.formatar_moeda(montante_final), delta=f"+ {utils.formatar_moeda(juros_acumulados)} em Juros Compostos", delta_color="normal")
            
            st.caption(f"Trilha do Projeto (Meta de {meses_totais} meses de disciplina financeira)")
            st.progress(0.05)

    st.markdown("---")
    st.markdown("<div id='ancora-compras'></div>", unsafe_allow_html=True)
    st.subheader("📋 Acompanhamento de Compras (Consolidado)")
    st.caption("Visão geral de todos os parcelamentos e financiamentos em andamento.")
    tab_vista, tab_parcelado, tab_financ = st.tabs(["💳 À Vista no Cartão", "📦 Parcelado no Cartão", "🏦 Financiamentos"])
    
    lista_vista = db.list_compras_por_tipo(user, forma_pagamento="Cartão de Crédito", somente_parceladas=False)
    lista_parcelado = db.list_compras_por_tipo(user, forma_pagamento="Cartão de Crédito", somente_parceladas=True)
    lista_financ = db.list_compras_por_tipo(user, forma_pagamento="Financiamento")

    if filtro_caixa != "Consolidado": 
        lista_vista = [x for x in lista_vista if x.get('caixa', 'PF (Pessoal)') == filtro_caixa]
        lista_parcelado = [x for x in lista_parcelado if x.get('caixa', 'PF (Pessoal)') == filtro_caixa]
        lista_financ = [x for x in lista_financ if x.get('caixa', 'PF (Pessoal)') == filtro_caixa]

    with tab_vista:
        st.dataframe(tabela_compras_df(lista_vista), width='stretch', hide_index=True)
    with tab_parcelado:
        st.dataframe(tabela_compras_df(lista_parcelado), width='stretch', hide_index=True)
    with tab_financ:
        st.dataframe(tabela_compras_df(lista_financ), width='stretch', hide_index=True)

    # --- NOVA ÁREA: GERENCIAMENTO RÁPIDO DO GRUPO DE COMPRAS ---
    todas_compras_agrupadas = lista_vista + lista_parcelado + lista_financ
    if todas_compras_agrupadas:
        st.write("")
        with st.container(border=True):
            st.markdown("#### 🛠️ Gerenciamento Rápido (Excluir Compras)")
            st.caption("Selecione uma compra da lista acima para destruir o histórico e apagar **TODAS** as suas parcelas de uma só vez (Ideal para consertar erros de lançamento como os da Moto).")
            
            opcoes_grp = {f"[{c['forma_pagamento']}] {c['descricao']} | Total: {utils.formatar_moeda(c['valor_total'])} | {c['parcela_total']}x": c['compra_grupo'] for c in todas_compras_agrupadas}
            sel_grp = st.selectbox("Selecione a compra que deseja excluir:", [None] + list(opcoes_grp.keys()), key="sel_grp_dash")
            
            if sel_grp:
                grp_id = opcoes_grp[sel_grp]
                col_act1, col_act2 = st.columns([1, 2])
                if col_act1.button("🗑️ Excluir TODAS as parcelas", type="primary", key="btn_del_grp"):
                    try:
                        db.delete_grupo(grp_id, user)
                        st.success("Compra e todas as suas parcelas foram apagadas permanentemente!")
                        st.rerun()
                    except PermissionError as e: 
                        st.error(str(e))
                col_act2.info("💡 Dica: Se errou o valor ou as parcelas na hora de registrar, basta excluir a compra inteira aqui e lançar novamente na aba Despesas.")

    st.markdown("---")
    st.markdown("<div id='ancora-edicao'></div>", unsafe_allow_html=True)
    st.subheader("✏️ Editor Avançado de Parcelas")
    st.caption("Acesse e modifique dados específicos de QUALQUER lançamento isolado do seu histórico (Ex: Se um mês você pagou com juros).")

    todas_despesas = db.list_despesas(user)
    
    if todas_despesas:
        opcoes_dict = {
            f"Venc: {d['data_competencia']} | {d['descricao']} ({d['parcela_atual']}/{d['parcela_total']}) | R$ {d['valor']} | ID {d['id']}": d["id"]
            for d in todas_despesas
        }
        
        escolha = st.selectbox("Busque a parcela que deseja corrigir:", [None] + list(opcoes_dict.keys()))
        
        if escolha:
            id_acao = opcoes_dict[escolha]
            desp_edit = next((d for d in todas_despesas if d["id"] == id_acao), None)
            
            if desp_edit:
                cartoes = db.list_cartoes(user)
                nomes_categorias = {c["nome"]: c["id"] for c in categorias}
                
                def _rotulo_cartao(c):
                    selo = utils.BANCOS_EMOJI.get(c.get("banco"), "") if c.get("banco") else ""
                    return f"{selo} — {c['nome']}" if selo else c["nome"]
                nomes_cartoes = {_rotulo_cartao(c): c["id"] for c in cartoes}
                
                with st.container(border=True):
                    st.markdown(f"### Ajustando: {desp_edit['descricao']}")
                    
                    with st.form("form_edit_dash"):
                        cx_edit1, cx_edit2 = st.columns(2)
                        idx_cx = OPCOES_CAIXA.index(desp_edit.get("caixa", "PF (Pessoal)")) if desp_edit.get("caixa") in OPCOES_CAIXA else 0
                        edit_caixa = cx_edit1.selectbox("Caixa", OPCOES_CAIXA, index=idx_cx)
                        
                        idx_resp = OPCOES_RESPONSAVEL.index(desp_edit.get("responsavel", "Conjunto")) if desp_edit.get("responsavel") in OPCOES_RESPONSAVEL else 0
                        edit_resp = cx_edit2.selectbox("Responsável", OPCOES_RESPONSAVEL, index=idx_resp)

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
                        
                        salvar_edicao = st.form_submit_button("💾 Salvar Alterações da Parcela")
                        
                        if salvar_edicao:
                            try:
                                novo_cat_id = nomes_categorias.get(edit_cat)
                                novo_cartao_id = nomes_cartoes.get(edit_cartao_nome) if edit_cartao_nome else None
                                db.edit_despesa(id_acao, edit_data_compra.isoformat(), edit_data_venc.isoformat(), novo_cat_id, edit_desc, edit_valor, edit_forma, novo_cartao_id, edit_caixa, edit_resp, user)
                                st.success("Lançamento atualizado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao editar: {e}")
                                
                    st.markdown("**🗑️ Exclusão Singular:**")
                    if st.button("🗑️ Apagar APENAS esta parcela", key="del_one"):
                        try:
                            db.delete_despesa(id_acao, user)
                            st.success("Parcela excluída.")
                            st.rerun()
                        except PermissionError as e: st.error(str(e))

elif pagina == "📥 Receitas":
    st.title("📥 Receitas (Entradas)")
    with st.form("form_receita", clear_on_submit=True):
        st.subheader("Nova Entrada")
        c1, c2, c3 = st.columns(3)
        data_receita = c1.date_input("Data", value=HOJE)
        origem = c2.selectbox("Origem", ORIGENS_RECEITA)
        caixa_rec = c3.selectbox("Caixa de Destino", OPCOES_CAIXA)
        
        c4, c5 = st.columns([1, 2])
        valor = c4.number_input("Valor (R$)", min_value=0.0, step=50.0, format="%.2f")
        observacao = c5.text_input("Observação (opcional)")
        
        enviado = st.form_submit_button("➕ Registrar Receita", type="primary")
        if enviado:
            if valor <= 0: st.error("Informe um valor maior que zero.")
            else:
                try:
                    db.add_receita(data_receita.isoformat(), origem, valor, observacao, caixa_rec, user_id=user.get("id"))
                    st.success("Receita registrada com sucesso!")
                except Exception as e: st.error(f"Não foi possível registrar a receita: {e}")

    st.markdown("---")
    st.subheader(f"Receitas de {utils.MESES_PT[mes_sel]}/{ano_sel}")
    receitas = db.list_receitas(user, ano_sel, mes_sel)
    df = utils.receitas_para_dataframe(receitas)
    if df.empty: st.info("Nenhuma receita lançada neste período.")
    else:
        df_show = pd.DataFrame(receitas)
        df_show["caixa"] = df_show["caixa"].fillna("PF (Pessoal)")
        df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
        st.dataframe(df_show[["id", "data", "caixa", "origem", "valor", "observacao"]], width='stretch', hide_index=True)
        id_excluir = st.selectbox("Excluir lançamento (selecione o ID)", [None] + df["id"].tolist())
        if id_excluir and st.button("🗑️ Excluir receita selecionada"):
            try:
                db.delete_receita(id_excluir, user)
                st.success("Receita excluída.")
                st.rerun()
            except PermissionError as e: st.error(str(e))

elif pagina == "📤 Despesas":
    st.title("📤 Despesas e Responsabilidades")
    st.caption("Centralize os lançamentos das suas duas frentes (PF/PJ) e divida o controle das contas com a sua esposa.")

    tab_lancar, tab_fixas, tab_cartoes = st.tabs(["📝 Lançar Despesa", "🔁 Despesas Fixas", "💳 Cartões"])

    with tab_lancar:
        categorias = db.list_categorias(user)
        cartoes = db.list_cartoes(user)
        nomes_categorias = {c["nome"]: c["id"] for c in categorias}

        def _rotulo_cartao(c):
            selo = utils.BANCOS_EMOJI.get(c.get("banco"), "") if c.get("banco") else ""
            return f"{selo} — {c['nome']}" if selo else c["nome"]
        nomes_cartoes = {_rotulo_cartao(c): c["id"] for c in cartoes}

        with st.container(border=True):
            st.subheader("Nova Despesa")
            c_cx1, c_cx2 = st.columns(2)
            caixa_desp = c_cx1.selectbox("Caixa Pagador", OPCOES_CAIXA, key="nova_cx")
            resp_desp = c_cx2.selectbox("Responsável", OPCOES_RESPONSAVEL, key="nova_resp")

            c1, c2 = st.columns(2)
            data_compra = c1.date_input("Data da compra/despesa", value=HOJE, key="nova_data")
            descricao = c2.text_input("Descrição", key="nova_desc")

            c3, c4 = st.columns(2)
            categoria_nome = c3.selectbox("Categoria", list(nomes_categorias.keys()), key="nova_cat")
            forma_pagamento = c4.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, key="nova_forma")

            cartao_nome = None
            if forma_pagamento in ("Cartão de Crédito", "Cartão de Débito"):
                if nomes_cartoes: cartao_nome = st.selectbox("Cartão utilizado", list(nomes_cartoes.keys()), key="novo_cartao")
                else: st.warning("Nenhum cartão cadastrado.")

            c5, c6 = st.columns(2)
            valor_total = c5.number_input("Valor total (R$)", min_value=0.0, step=10.0, format="%.2f", key="novo_valor")
            
            parcelas = 1
            data_vencimento = data_compra
            
            if forma_pagamento in ("Cartão de Crédito", "Financiamento"):
                max_parcelas = 48 if forma_pagamento == "Cartão de Crédito" else 420
                parcelas = c6.number_input("Quantidade de parcelas", min_value=1, max_value=max_parcelas, value=1, step=1, key="nova_parc")
                st.markdown("👇 **Data do Vencimento**")
                data_vencimento = st.date_input("Informe a data de vencimento da 1ª parcela", value=data_compra, key="nova_venc")

            enviado = st.button("➕ Registrar Despesa", type="primary")

            if enviado:
                if valor_total <= 0: st.error("Informe um valor maior que zero.")
                elif not descricao.strip(): st.error("Informe uma descrição.")
                else:
                    try:
                        categoria_id = nomes_categorias.get(categoria_nome)
                        cartao_id = nomes_cartoes.get(cartao_nome) if cartao_nome else None
                        
                        db.add_despesa(data_compra, categoria_id, descricao, valor_total,
                                        forma_pagamento, cartao_id, parcelas, 
                                        primeira_competencia=data_vencimento, caixa=caixa_desp, responsavel=resp_desp, user_id=user.get("id"))

                        if parcelas > 1: st.success("Despesa parcelada registrada com sucesso!")
                        else: st.success("Despesa registrada com sucesso!")
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
            df_show = pd.DataFrame(despesas)
            df_show["caixa"] = df_show["caixa"].fillna("PF (Pessoal)")
            df_show["responsavel"] = df_show["responsavel"].fillna("Conjunto")
            df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
            df_show["parcela"] = df_show["parcela_atual"].astype(str) + "/" + df_show["parcela_total"].astype(str)
            df_show = df_show[["id", "caixa", "responsavel", "data_competencia", "categoria_nome", "descricao", "valor", "forma_pagamento", "cartao_nome", "parcela"]]
            df_show.columns = ["ID", "Caixa", "Responsável", "Vencimento", "Categoria", "Descrição", "Valor", "Pagamento", "Cartão", "Parcela"]
            st.dataframe(df_show, width='stretch', hide_index=True)

    with tab_fixas:
        st.caption("Gere os lançamentos automáticos de cada caixa e responsável.")
        categorias = db.list_categorias(user)
        cartoes = db.list_cartoes(user)
        nomes_categorias = {c["nome"]: c["id"] for c in categorias}
        def _rotulo_cartao_fixa(c):
            selo = utils.BANCOS_EMOJI.get(c.get("banco"), "") if c.get("banco") else ""
            return f"{selo} — {c['nome']}" if selo else c["nome"]
        nomes_cartoes = {_rotulo_cartao_fixa(c): c["id"] for c in cartoes}

        with st.form("form_fixa", clear_on_submit=True):
            cx_f1, cx_f2 = st.columns(2)
            caixa_fixa = cx_f1.selectbox("Caixa", OPCOES_CAIXA)
            resp_fixa = cx_f2.selectbox("Responsável", OPCOES_RESPONSAVEL)
            
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
                        db.add_despesa_fixa(descricao, nomes_categorias[categoria_nome], valor, forma_pagamento, cartao_id, dia_vencimento, caixa_fixa, resp_fixa, user_id=user.get("id"))
                        st.success("Despesa fixa cadastrada!")
                    except Exception as e: st.error(f"Erro: {e}")

        st.markdown("---")
        st.subheader("Despesas fixas cadastradas")
        fixas = db.list_despesas_fixas(user, somente_ativas=False)
        if not fixas: st.info("Nenhuma despesa fixa cadastrada.")
        else:
            df_fixas = pd.DataFrame(fixas)
            df_show = df_fixas[["id", "caixa", "responsavel", "descricao", "categoria_nome", "valor", "forma_pagamento", "dia_vencimento", "ativa"]].copy()
            df_show["caixa"] = df_show["caixa"].fillna("PF (Pessoal)")
            df_show["responsavel"] = df_show["responsavel"].fillna("Conjunto")
            df_show["valor"] = df_show["valor"].apply(utils.formatar_moeda)
            df_show["ativa"] = df_show["ativa"].apply(lambda x: "✅ Ativa" if x else "⏸️ Pausada")
            df_show.columns = ["ID", "Caixa", "Responsável", "Descrição", "Categoria", "Valor", "Pagamento", "Dia Venc.", "Status"]
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
        st.caption("O selo abaixo (emoji colorido) é apenas uma identificação visual.")
        with st.form("form_cartao", clear_on_submit=True):
            c1, c2 = st.columns(2)
            banco = c1.selectbox("Banco / Instituição", list(utils.BANCOS_EMOJI.keys()), format_func=lambda b: utils.BANCOS_EMOJI[b])
            nome = c2.text_input("Apelido do cartão")
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
    
    st.markdown("""
        <style>
        @media print {
            .css-18ni7ap { display: none !important; }
            header { display: none !important; }
            .stButton { display: none !important; }
            .stRadio { display: none !important; }
        }
        </style>
        <button onclick="window.print()" style="padding:10px 15px; border-radius:5px; background-color:#00FFAA; color:#111; font-weight:bold; border:none; cursor:pointer; width:100%; margin-bottom: 20px;">
            🖨️ Imprimir / Salvar Extrato em PDF
        </button>
    """, unsafe_allow_html=True)
    
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

    st.subheader("📥 Receitas Consolidadas")
    st.dataframe(df_r, width='stretch', hide_index=True)
    st.subheader("📤 Despesas Consolidadas")
    st.dataframe(df_d, width='stretch', hide_index=True)

    st.markdown("---")
    st.subheader("⬇️ Exportar dados Brutos")
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
    st.write("Sistema de ERP Financeiro Integrado\n\n- Modo local: SQLite (`financas.db`) na sua máquina.\n- Modo nuvem: Turso (compatível com SQLite), sem perda de dados em reinícios.")

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
