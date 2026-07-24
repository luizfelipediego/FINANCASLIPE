💰 Sistema de Gestão Financeira Pessoal e Familiar
Sistema completo de controle financeiro construído em Python + Streamlit + SQLite.
Por que essa stack?
Camada	Tecnologia	Motivo
Interface	Streamlit	Gera dashboards visuais e interativos (gráficos, formulários, tabelas, barras de progresso) com muito pouco código, sem precisar de HTML/CSS/JS.
Banco de dados	SQLite	Arquivo único (`financas.db`), zero configuração de servidor, ideal para uso pessoal/familiar. Fácil de migrar para Postgres/MySQL no futuro se necessário.
Gráficos	Plotly Express	Gráficos interativos (pizza, linha) prontos para o dashboard.
Exportação	Pandas + OpenPyXL	Exportação nativa para CSV e Excel (.xlsx).
Essa combinação entrega um app visual, local, gratuito e sem dependências externas (nenhum dado sai da sua máquina).
---
📁 Estrutura dos arquivos
```
financas_app/
├── app.py            # Interface Streamlit (todas as páginas/telas)
├── db.py             # Camada de banco de dados e regras de negócio
├── utils.py           # Formatação de moeda, datas e cálculo de resumo mensal
├── requirements.txt   # Dependências do projeto
└── README.md           # Este arquivo
```
Ao rodar pela primeira vez, o sistema cria automaticamente o arquivo `financas.db`
na mesma pasta, já com categorias padrão (Mercado, Saúde/Remédios, Estudos/Educação,
Lazer, Moradia, Veículo, Outros).
---
🔧 Instalação
1. Pré-requisitos
Python 3.9 ou superior instalado (python.org)
2. Baixe os arquivos
Coloque `app.py`, `db.py`, `utils.py` e `requirements.txt` na mesma pasta.
3. (Recomendado) Crie um ambiente virtual
```bash
python3 -m venv venv

# Ativar no Linux/Mac:
source venv/bin/activate

# Ativar no Windows:
venv\Scripts\activate
```
4. Instale as dependências
```bash
pip install -r requirements.txt
```
5. Execute o sistema
```bash
streamlit run app.py
```
O navegador abrirá automaticamente em `http://localhost:8501`. Se não abrir,
copie esse endereço e cole no navegador manualmente.
---
🖥️ Como usar
Cadastre cartões (menu "💳 Cartões") informando dia de fechamento e vencimento.
Cadastre categorias e tetos de gasto (menu "🏷️ Categorias e Orçamento").
Configure o % de reserva desejado (menu "⚙️ Configurações").
Registre receitas e despesas normalmente. Em compras no cartão de crédito,
informe o número de parcelas — o sistema projeta automaticamente cada parcela
no mês correto, respeitando a data de fechamento da fatura.
Cadastre despesas fixas (Aluguel, Internet, etc.) uma única vez e use o
botão "Gerar Despesas Fixas do Mês" sempre que virar o mês (não duplica se
já tiver sido gerado).
Acompanhe tudo pelo Dashboard: receitas x despesas, reserva, saldo livre,
gráficos e alertas de teto de gastos (verde < 80%, laranja 80–99%, vermelho ≥ 100%).
Use "📁 Relatórios e Exportação" para filtrar por dia/mês/ano e baixar CSV/Excel.
---
📌 Regras de negócio implementadas
Competência de cartão de crédito: se a compra ocorrer após o dia de
fechamento, a 1ª parcela é automaticamente lançada na fatura do mês seguinte.
Parcelamento: cada parcela é uma linha própria com sua competência
(mês/ano) calculada automaticamente; a última parcela absorve eventuais
diferenças de arredondamento centavo a centavo.
Reserva automática: a cada receita lançada, o sistema recalcula em tempo
real o valor a destinar à reserva, com base no % configurado, sobre o total
de receitas do mês.
Despesas fixas: cadastradas uma única vez como "modelo"; a duplicação
para o mês corrente é feita sob demanda (botão), evitando lançamentos
duplicados.
Alertas de orçamento: cada categoria pode ter um teto mensal; o dashboard
mostra barra de progresso colorida e alerta textual ao atingir 80% e 100%.
---
🔄 Resetar os dados (modo local)
Para começar do zero, basta apagar o arquivo `financas.db` gerado na pasta.
Ele será recriado automaticamente na próxima execução.
⚠️ Nota sobre múltiplos usuários
Este sistema foi desenhado para uso local/pessoal/familiar. Para uso simultâneo
por várias pessoas em rede, o modo Turso (nuvem) descrito abaixo já resolve o
compartilhamento — todos os dispositivos leem/gravam no mesmo banco.
---
☁️ Banco em nuvem (Turso) — para não perder dados quando hospedado online
Se você for publicar o app no Streamlit Community Cloud (ou qualquer outro
serviço com disco não-persistente), configure o Turso para garantir que
nenhum lançamento seja perdido, mesmo que o app reinicie.
O sistema já vem pronto para isso: se as credenciais abaixo existirem, ele usa
o Turso automaticamente; se não existirem, continua usando SQLite local sem
nenhuma mudança de comportamento.
1. Criar uma conta e um banco no Turso (gratuito)
Acesse turso.tech e crie uma conta gratuita.
No painel (dashboard), clique em "Create Database", dê um nome
(ex: `financas-familia`) e escolha uma região próxima de você.
Na página do banco criado, copie:
A Database URL (algo como `libsql://financas-familia-suaorg.turso.io`)
Um Auth Token (token de autenticação — gere um na própria página, em
"Tokens" ou "Generate token")
2. Configurar as credenciais
No Streamlit Community Cloud:
Abra seu app já publicado → menu ⋮ (três pontinhos) → Settings → Secrets.
Cole o seguinte, substituindo pelos seus valores reais:
```toml
   TURSO_DATABASE_URL = "libsql://financas-familia-suaorg.turso.io"
   TURSO_AUTH_TOKEN = "seu-token-aqui"
   ```
Salve. O app reinicia sozinho e passa a usar o Turso automaticamente.
Para testar localmente com o Turso (opcional):
Copie o arquivo `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`.
Preencha com suas credenciais reais.
Rode `streamlit run app.py` normalmente — os dados agora vão direto para a nuvem.
⚠️ Nunca suba o arquivo `.streamlit/secrets.toml` (com credenciais reais) para
o GitHub público — apenas o `.example` deve ir para o repositório. Adicione
`.streamlit/secrets.toml` ao seu `.gitignore`.
3. Como confirmar que está funcionando
Abra o menu "⚙️ Configurações" dentro do app. Na seção "🗄️ Status do
Banco de Dados", você verá:
☁️ Turso (nuvem) → credenciais configuradas corretamente, dados seguros.
💻 SQLite local → nenhuma credencial encontrada, dados só existem no
disco local (podem se perder se o app reiniciar em um servidor na nuvem).
