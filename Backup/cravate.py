import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date

# ── CONFIG DA PÁGINA ──
st.set_page_config(page_title="Cravate Shop - Gestão de Vendas", layout="wide")

# ── BANCO DE DADOS ──
def get_conn():
    return sqlite3.connect('cravate_shop.db', check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Tabela de produtos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            preco REAL NOT NULL,
            categoria TEXT NOT NULL
        )
    """)

    # Verifica se a tabela vendas existe e qual estrutura tem
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vendas'")
    tabela_existe = cur.fetchone()

    if tabela_existe:
        # Vê se a coluna 'itens' já existe (estrutura nova)
        cur.execute("PRAGMA table_info(vendas)")
        colunas = [row[1] for row in cur.fetchall()]
        
        if 'itens' not in colunas:
            # ═══ ESTRUTURA ANTIGA → migrar ═══
            # Cria tabela nova
            cur.execute("""
                CREATE TABLE vendas_nova (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    itens TEXT,
                    quantidade_total INTEGER,
                    valor_bruto REAL,
                    desconto REAL,
                    valor_final REAL,
                    data TEXT,
                    cliente_nome TEXT
                )
            """)
            # Copia dados da tabela antiga convertendo os campos
            cur.execute("""
                INSERT INTO vendas_nova (id, itens, quantidade_total, valor_bruto, desconto, valor_final, data, cliente_nome)
                SELECT id, produto_nome, quantidade, valor_total, 0, valor_total, data, cliente_nome FROM vendas
            """)
            # Remove tabela antiga e renomeia a nova
            cur.execute("DROP TABLE vendas")
            cur.execute("ALTER TABLE vendas_nova RENAME TO vendas")
    else:
        # ═══ TABELA NOVA (primeira vez) ═══
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                itens TEXT,
                quantidade_total INTEGER,
                valor_bruto REAL,
                desconto REAL,
                valor_final REAL,
                data TEXT,
                cliente_nome TEXT
            )
        """)

    # Produtos iniciais
    cur.execute("SELECT COUNT(*) FROM produtos")
    if cur.fetchone()[0] == 0:
        produtos = [
            ('Gravata Estampada', 30.00, 'Gravatas'),
            ('Gravata Lisa', 25.00, 'Gravatas'),
            ('Gravata Seda Réplica', 50.00, 'Gravatas'),
            ('Gravata Seda', 130.00, 'Gravatas'),
            ('Cinto Automático', 55.00, 'Cintos'),
            ('Prendedor de Gravata', 7.00, 'Acessórios'),
            ('Extensor de Colarinho', 15.00, 'Acessórios'),
            ('Carteira', 30.00, 'Carteiras'),
            ('Meia', 10.00, 'Meias')
        ]
        cur.executemany(
            "INSERT INTO produtos (nome, preco, categoria) VALUES (?, ?, ?)",
            produtos
        )
    conn.commit()
    conn.close()

init_db()

# ── FUNÇÕES AUXILIARES ──
def carregar_produtos():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM produtos ORDER BY categoria, nome", conn)
    conn.close()
    return df

def registrar_venda(itens, qtd_total, valor_bruto, desconto, valor_final, data_venda, cliente):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO vendas (itens, quantidade_total, valor_bruto, desconto, valor_final, data, cliente_nome)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (itens, qtd_total, valor_bruto, desconto, valor_final, data_venda, cliente))
    conn.commit()
    conn.close()

def carregar_vendas():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM vendas ORDER BY id DESC", conn)
    conn.close()
    return df

# ── CSS ──
st.markdown("""
<style>
    * { font-family: 'Segoe UI', sans-serif; }
    .main { background-color: #0e1117; color: #ffffff; }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e293b;
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        background-color: #3b82f6 !important;
        color: white !important;
    }

    .card {
        background: #1e293b;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 15px;
        border-left: 6px solid #475569;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
    }
    .card.verde { border-left-color: #10b981; }
    .card.amarelo { border-left-color: #f59e0b; }
    .card.vermelho { border-left-color: #ef4444; }

    .kpi-label { font-size: 0.8rem; color: #94a3b8; font-weight: 600; text-transform: uppercase; }
    .kpi-value { font-size: 1.8rem; font-weight: 800; margin: 5px 0; }
    .kpi-meta { font-size: 0.75rem; color: #64748b; }

    .semaforo {
        display: inline-block;
        padding: 2px 12px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 700;
        margin-top: 8px;
    }
    .semaforo.verde { background: #064e3b; color: #34d399; }
    .semaforo.amarelo { background: #78350f; color: #fbbf24; }
    .semaforo.vermelho { background: #7f1d1d; color: #f87171; }
</style>
""", unsafe_allow_html=True)

# ── SIDEBAR ──
st.sidebar.markdown("## 🧣 Cravate Shop")
st.sidebar.markdown("Sistema de Gestão de Vendas")
st.sidebar.markdown("---")
st.sidebar.markdown("### Produtos")
df_produtos = carregar_produtos()
for _, row in df_produtos.iterrows():
    st.sidebar.markdown(f"- **{row['nome']}** — R$ {row['preco']:,.2f} *({row['categoria']})*")

# ── ABAS ──
tab1, tab2, tab3 = st.tabs(["📝 Registrar Venda", "📊 Relatórios", "📋 Catálogo"])

# ════════════════════════════════════════
# ABA 1 — REGISTRAR VENDA
# ════════════════════════════════════════
with tab1:
    col_form, col_hist = st.columns([1, 1.5])

    with col_form:
        st.markdown("### Nova Venda")

        produtos_selecionados = st.multiselect(
            "Produtos",
            df_produtos['nome'].tolist(),
            placeholder="Selecione os produtos..."
        )

        if produtos_selecionados:
            itens_venda = []
            valor_bruto = 0
            qtd_total = 0

            st.markdown("**Quantidades:**")
            cols_qtd = st.columns(len(produtos_selecionados))
            for i, prod_nome in enumerate(produtos_selecionados):
                row_p = df_produtos[df_produtos['nome'] == prod_nome].iloc[0]
                qtd = cols_qtd[i].number_input(
                    prod_nome,
                    min_value=1,
                    value=1,
                    key=f"qtd_{prod_nome}",
                    label_visibility="collapsed"
                )
                subtotal = row_p['preco'] * qtd
                valor_bruto += subtotal
                qtd_total += qtd
                itens_venda.append(f"{prod_nome} x{qtd} (R$ {subtotal:,.2f})")

            desconto = st.number_input(
                "Desconto (R$)",
                min_value=0.0,
                max_value=float(valor_bruto),
                value=0.0,
                step=1.0,
                format="%.2f"
            )

            valor_final = valor_bruto - desconto

            st.markdown(f"""
            <div style="background:#1e293b; padding:20px; border-radius:10px; border:1px solid #334155; margin:15px 0;">
                <p style="margin:0; color:#94a3b8;">Valor Bruto</p>
                <h3 style="margin:0; color:#94a3b8;">R$ {valor_bruto:,.2f}</h3>
                <p style="margin:10px 0 0 0; color:#94a3b8;">Desconto</p>
                <h3 style="margin:0; color:#ef4444;">- R$ {desconto:,.2f}</h3>
                <hr style="border-color:#334155; margin:15px 0;">
                <p style="margin:0; color:#3b82f6; font-size:1.2rem; font-weight:700;">Total a Pagar</p>
                <h2 style="margin:0; color:#3b82f6;">R$ {valor_final:,.2f}</h2>
            </div>
            """, unsafe_allow_html=True)

            data_venda = st.date_input("Data da Venda", value=date.today())
            cliente = st.text_input("Nome do Cliente", placeholder="Opcional")

            if st.button("Confirmar Venda", type="primary", use_container_width=True):
                itens_str = " | ".join(itens_venda)
                registrar_venda(
                    itens_str,
                    qtd_total,
                    valor_bruto,
                    desconto,
                    valor_final,
                    data_venda.strftime("%Y-%m-%d"),
                    cliente if cliente else "Consumidor"
                )
                st.success("Venda registrada com sucesso!")
                st.rerun()
        else:
            st.info("Selecione ao menos um produto para iniciar a venda.")

    with col_hist:
        st.markdown("### Últimas Vendas")
        df_vendas = carregar_vendas()
        if not df_vendas.empty:
            exibir = df_vendas[['data', 'itens', 'valor_bruto', 'desconto', 'valor_final', 'cliente_nome']].head(20)
            exibir.columns = ['Data', 'Itens', 'Valor Bruto', 'Desconto', 'Total', 'Cliente']
            st.dataframe(exibir, use_container_width=True, hide_index=True)
            total_periodo = df_vendas.head(20)['valor_final'].sum()
            st.info(f"Soma das últimas 20 vendas: R$ {total_periodo:,.2f}")
        else:
            st.info("Nenhuma venda registrada ainda.")

# ════════════════════════════════════════
# ABA 2 — RELATÓRIOS
# ════════════════════════════════════════
with tab2:
    st.markdown("### Dashboard Executivo")
    df_v = carregar_vendas()

    if not df_v.empty:
        df_v['data'] = pd.to_datetime(df_v['data'])
        df_v['mes'] = df_v['data'].dt.month
        df_v['ano'] = df_v['data'].dt.year

        col_f1, col_f2 = st.columns(2)
        anos_disponiveis = sorted(df_v['ano'].unique(), reverse=True)
        ano_sel = col_f1.selectbox("Ano", anos_disponiveis)
        mes_sel = col_f2.selectbox("Mês", range(1, 13), index=datetime.now().month - 1)

        df_filtro = df_v[(df_v['ano'] == ano_sel) & (df_v['mes'] == mes_sel)]

        if not df_filtro.empty:
            qtd_vendas = int(df_filtro['quantidade_total'].sum())
            receita = float(df_filtro['valor_final'].sum())
            qtd_clientes = df_filtro['cliente_nome'].nunique()
            ticket = receita / qtd_vendas if qtd_vendas > 0 else 0
            total_desconto = float(df_filtro['desconto'].sum())

            meta_vendas, meta_receita, meta_ticket, meta_clientes = 50, 2000.0, 80.0, 30

            def status(v, m):
                if v >= m: return "verde"
                if v >= m * 0.7: return "amarelo"
                return "vermelho"

            k1, k2, k3, k4 = st.columns(4)
            cards = [
                (k1, "Vendas no Mês", qtd_vendas, meta_vendas),
                (k2, "Receita Líquida", f"R$ {receita:,.2f}", f"R$ {meta_receita:,.0f}"),
                (k3, "Ticket Médio", f"R$ {ticket:,.2f}", f"R$ {meta_ticket:,.0f}"),
                (k4, "Clientes", qtd_clientes, meta_clientes),
            ]
            vals = [qtd_vendas, receita, ticket, qtd_clientes]
            metas = [meta_vendas, meta_receita, meta_ticket, meta_clientes]

            for (col, label, val, meta), v, m in zip(cards, vals, metas):
                sts = status(v, m)
                col.markdown(f"""
                <div class="card {sts}">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{val}</div>
                    <div class="kpi-meta">Meta: {meta}</div>
                    <div class="semaforo {sts}">{sts.upper()}</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown(f"<p style='color:#94a3b8;'>Desconto total concedido no período: <strong style='color:#ef4444;'>R$ {total_desconto:,.2f}</strong></p>", unsafe_allow_html=True)

            st.markdown("### 📈 Receita Diária")
            df_dia = df_filtro.groupby('data')['valor_final'].sum().reset_index()
            import altair as alt
            chart = alt.Chart(df_dia).mark_bar(color='#3b82f6').encode(
                x=alt.X('data:T', title='Data'),
                y=alt.Y('valor_final:Q', title='Receita (R$)'),
                tooltip=['data', 'valor_final']
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)

            st.markdown("### 💡 Insights Executivos")
            st.markdown(f"""
            <div class="card verde">
                <strong>🔍 Resumo do Período</strong><br><br>
                • <strong>{qtd_vendas}</strong> itens vendidos para <strong>{qtd_clientes}</strong> clientes<br>
                • Receita líquida: <strong>R$ {receita:,.2f}</strong><br>
                • Descontos concedidos: <strong>R$ {total_desconto:,.2f}</strong><br>
                • Ticket médio: <strong>R$ {ticket:,.2f}</strong>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Nenhuma venda no período selecionado.")
    else:
        st.info("Nenhuma venda registrada. Cadastre vendas na aba anterior.")

# ════════════════════════════════════════
# ABA 3 — CATÁLOGO
# ════════════════════════════════════════
with tab3:
    st.markdown("### Catálogo de Produtos")
    for _, row in df_produtos.iterrows():
        st.markdown(f"""
        <div class="card" style="border-left-color: #3b82f6;">
            <strong>{row['nome']}</strong> — R$ {row['preco']:,.2f}
            <span style="float:right; background:#334155; padding:2px 12px; border-radius:12px; font-size:0.75rem;">
                {row['categoria']}
            </span>
        </div>
        """, unsafe_allow_html=True)