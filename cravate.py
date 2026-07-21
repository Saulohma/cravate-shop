import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import altair as alt
import math
import hashlib
import hmac
import os
from sqlalchemy import create_engine, text

# ═══════════════════════════════════════════
# CONFIGURAÇÃO DA PÁGINA
# ═══════════════════════════════════════════
st.set_page_config(page_title="Cravate Shop - Gestão de Vendas", layout="wide")

# ═══════════════════════════════════════════
# CONEXÃO NEON (PostgreSQL)
# ═══════════════════════════════════════════
@st.cache_resource
def get_engine():
    """Conecta ao Neon PostgreSQL via string de conexão"""
    if "neon" in st.secrets and "connection_string" in st.secrets["neon"]:
        conn_str = st.secrets["neon"]["connection_string"]
    else:
        conn_str = os.environ.get("NEON_CONNECTION_STRING")
        if not conn_str:
            st.error("❌ String de conexão do Neon não encontrada!")
            st.stop()
    return create_engine(conn_str, pool_pre_ping=True, pool_recycle=300)

def get_conn():
    return get_engine().connect()

# ═══════════════════════════════════════════
# FUNÇÕES DE LOGIN
# ═══════════════════════════════════════════
def fazer_hash(senha, salt=None):
    """Cria hash SHA-256 da senha com salt"""
    if salt is None:
        salt = os.urandom(16).hex()
    hash_obj = hashlib.sha256()
    hash_obj.update((salt + senha).encode('utf-8'))
    return f"{salt}${hash_obj.hexdigest()}"

def verificar_senha(senha, hash_completo):
    """Verifica se a senha corresponde ao hash armazenado"""
    if '$' not in hash_completo:
        return False
    salt, hash_esperado = hash_completo.split('$', 1)
    hash_obj = hashlib.sha256()
    hash_obj.update((salt + senha).encode('utf-8'))
    return hmac.compare_digest(hash_obj.hexdigest(), hash_esperado)

def init_usuarios():
    """Cria tabela de usuários e insere admin padrão"""
    conn = get_conn()

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'cliente',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))

    # Admin padrão — sempre garante que existe
    hash_admin = fazer_hash("admin123")
    conn.execute(
        text("""
            INSERT INTO usuarios (email, senha_hash, nome, tipo) 
            VALUES (:email, :hash, :nome, :tipo)
            ON CONFLICT (email) DO UPDATE 
            SET senha_hash = :hash2, nome = :nome2, tipo = :tipo2
        """),
        {
            "email": "admin@cravate.com",
            "hash": hash_admin,
            "nome": "Administrador",
            "tipo": "admin",
            "hash2": hash_admin,
            "nome2": "Administrador",
            "tipo2": "admin"
        }
    )
    conn.commit()
    conn.close()

def autenticar(email, senha):
    """Autentica o usuário e retorna os dados ou False"""
    conn = get_conn()
    resultado = conn.execute(
        text("SELECT id, email, senha_hash, nome, tipo FROM usuarios WHERE email = :email"),
        {"email": email}
    ).fetchone()
    conn.close()
    
    if resultado and verificar_senha(senha, resultado[2]):
        return {"id": resultado[0], "email": resultado[1], "nome": resultado[3], "tipo": resultado[4]}
    return False

def cadastrar_usuario(email, senha, nome, tipo="cliente"):
    """Cadastra um novo usuário"""
    conn = get_conn()
    try:
        hash_senha = fazer_hash(senha)
        conn.execute(
            text("INSERT INTO usuarios (email, senha_hash, nome, tipo) VALUES (:email, :hash, :nome, :tipo)"),
            {"email": email, "hash": hash_senha, "nome": nome, "tipo": tipo}
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

# ═══════════════════════════════════════════
# BANCO DE DADOS (Tabelas)
# ═══════════════════════════════════════════
def init_db():
    conn = get_conn()
    
    # Produtos
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS produtos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            preco REAL NOT NULL,
            categoria TEXT NOT NULL,
            estoque INTEGER DEFAULT 0,
            estoque_minimo INTEGER DEFAULT 5
        )
    """))
    
    # Vendas (com usuario_id para multitenant)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vendas (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER,
            itens TEXT,
            quantidade_total INTEGER,
            valor_bruto REAL,
            desconto REAL,
            valor_final REAL,
            data TEXT,
            cliente_nome TEXT
        )
    """))
    
    # Produtos iniciais
    resultado = conn.execute(text("SELECT COUNT(*) FROM produtos")).scalar()
    if resultado == 0:
        produtos = [
            ('Gravata Estampada', 30.00, 'Gravatas', 50, 5),
            ('Gravata Lisa', 25.00, 'Gravatas', 50, 5),
            ('Gravata Seda Réplica', 50.00, 'Gravatas', 30, 5),
            ('Gravata Seda', 130.00, 'Gravatas', 20, 3),
            ('Cinto Automático', 55.00, 'Cintos', 30, 5),
            ('Prendedor de Gravata', 7.00, 'Acessórios', 100, 10),
            ('Extensor de Colarinho', 15.00, 'Acessórios', 50, 10),
            ('Carteira', 30.00, 'Carteiras', 30, 5),
            ('Meia', 10.00, 'Meias', 60, 10)
        ]
        for p in produtos:
            conn.execute(
                text("INSERT INTO produtos (nome, preco, categoria, estoque, estoque_minimo) VALUES (:nome, :preco, :categoria, :estoque, :minimo)"),
                {"nome": p[0], "preco": p[1], "categoria": p[2], "estoque": p[3], "minimo": p[4]}
            )
    
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════
# FUNÇÕES DO SISTEMA
# ═══════════════════════════════════════════
def carregar_produtos():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM produtos ORDER BY categoria, nome", conn)
    conn.close()
    return df

def carregar_vendas(usuario_id=None):
    conn = get_conn()
    if usuario_id:
        df = pd.read_sql_query(f"SELECT * FROM vendas WHERE usuario_id = {usuario_id} ORDER BY id DESC", conn)
    else:
        df = pd.read_sql_query("SELECT * FROM vendas ORDER BY id DESC", conn)
    conn.close()
    return df

def editar_produto(produto_id, nova_qtd, novo_minimo, novo_preco):
    conn = get_conn()
    conn.execute(
        text("UPDATE produtos SET estoque = :qtd, estoque_minimo = :min, preco = :preco WHERE id = :id"),
        {"qtd": nova_qtd, "min": novo_minimo, "preco": novo_preco, "id": produto_id}
    )
    conn.commit()
    conn.close()

def baixar_estoque(produto_id, qtd):
    conn = get_conn()
    conn.execute(
        text("UPDATE produtos SET estoque = estoque - :qtd WHERE id = :id"),
        {"qtd": qtd, "id": produto_id}
    )
    conn.commit()
    conn.close()

def registrar_venda(usuario_id, itens, qtd_total, valor_bruto, desconto, valor_final, data_venda, cliente):
    conn = get_conn()
    conn.execute(
        text("""INSERT INTO vendas (usuario_id, itens, quantidade_total, valor_bruto, desconto, valor_final, data, cliente_nome) 
                VALUES (:uid, :itens, :qtd, :bruto, :desc, :final, :data, :cliente)"""),
        {"uid": usuario_id, "itens": itens, "qtd": qtd_total, 
         "bruto": float(valor_bruto),
         "desc": float(desconto), 
         "final": float(valor_final), 
         "data": data_venda, "cliente": cliente}
    )
    conn.commit()
    conn.close()
    atualizar_estoque_minimo_automatico()

def atualizar_estoque_minimo_automatico():
    """Calcula o estoque mínimo baseado na média mensal de vendas dos últimos 3 meses"""
    conn = get_conn()
    conn.execute(text("""
        UPDATE produtos SET estoque_minimo = GREATEST(3, CEIL(
            COALESCE((SELECT SUM(v.quantidade_total) / 3.0 FROM vendas v 
                       WHERE v.data >= :data_limite AND v.itens LIKE '%' || p.nome || '%'), 0) * 2
        ))
        FROM produtos p
        WHERE produtos.id = p.id
    """), {"data_limite": (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")})
    conn.commit()
    conn.close()

def deletar_usuario(user_id):
    """Deleta um usuário e suas vendas"""
    conn = get_conn()
    try:
        conn.execute(text("DELETE FROM vendas WHERE usuario_id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM usuarios WHERE id = :uid AND tipo != 'admin'"), {"uid": user_id})
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()

def resetar_sistema():
    """Reseta o sistema: limpa vendas, usuarios (menos admin), e restaura estoque inicial"""
    conn = get_conn()
    try:
        # Limpa vendas e usuarios não-admin
        conn.execute(text("DELETE FROM vendas"))
        conn.execute(text("DELETE FROM usuarios WHERE tipo != 'admin'"))

        # Restaura estoque inicial dos produtos
        conn.execute(text("""
            UPDATE produtos SET estoque = CASE nome
                WHEN 'Gravata Estampada' THEN 50
                WHEN 'Gravata Lisa' THEN 50
                WHEN 'Gravata Seda Réplica' THEN 30
                WHEN 'Gravata Seda' THEN 20
                WHEN 'Cinto Automático' THEN 30
                WHEN 'Prendedor de Gravata' THEN 100
                WHEN 'Extensor de Colarinho' THEN 50
                WHEN 'Carteira' THEN 30
                WHEN 'Meia' THEN 60
                ELSE estoque
            END
        """))
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


def carregar_usuarios():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, email, nome, tipo, created_at FROM usuarios ORDER BY id", conn)
    conn.close()
    return df

# ═══════════════════════════════════════════
# DATAS COMEMORATIVAS
# ═══════════════════════════════════════════
def calcular_dia_dos_pais(ano):
    d = date(ano, 8, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7 + 7)

def calcular_dia_das_maes(ano):
    d = date(ano, 5, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7 + 7)

def calcular_black_friday(ano):
    d = date(ano, 11, 30)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d

def obter_datas_comemorativas():
    hoje = date.today()
    ano = hoje.year
    datas = [
        ("🎉 Ano Novo", date(ano, 1, 1), "Promoção de Ano Novo"),
        ("💕 Dia dos Namorados", date(ano, 6, 12), "Coleção especial para presentear"),
        ("👩 Dia das Mães", calcular_dia_das_maes(ano), "Gravatas e acessórios para presente"),
        ("👨 Dia dos Pais", calcular_dia_dos_pais(ano), "Gravatas e cintos para o pai"),
        ("🧒 Dia das Crianças", date(ano, 10, 12), "Acessórios divertidos"),
        ("🤝 Dia do Cliente", date(ano, 9, 15), "Descontos especiais para clientes fiéis"),
        ("🎄 Natal", date(ano, 12, 25), "Kits de presente de Natal"),
        ("🛍️ Black Friday", calcular_black_friday(ano), "Grandes descontos em todo o estoque"),
    ]
    resultados = []
    for nome, data_evento, sugestao in datas:
        dias_restantes = (data_evento - hoje).days
        if dias_restantes >= -30:
            resultados.append((nome, data_evento, dias_restantes, sugestao))
    return sorted(resultados, key=lambda x: x[2])

# ═══════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════
st.markdown("""
<style>
    * { font-family: 'Segoe UI', sans-serif; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] { background-color: #1e293b; border-radius: 8px 8px 0 0; padding: 10px 20px; color: #94a3b8; }
    .stTabs [aria-selected="true"] { background-color: #3b82f6 !important; color: white !important; }
    .card { background: #1e293b !important; border-radius: 12px; padding: 20px; margin-bottom: 15px; border-left: 6px solid #475569; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); color: #ffffff !important; }
    .card * { color: #ffffff !important; }
    .card .kpi-meta { color: #94a3b8 !important; }
    .card .kpi-label { color: #94a3b8 !important; }
    .card.verde { border-left-color: #10b981; }
    .card.amarelo { border-left-color: #f59e0b; }
    .card.vermelho { border-left-color: #ef4444; }
    .kpi-label { font-size: 0.8rem; color: #94a3b8 !important; font-weight: 600; text-transform: uppercase; }
    .kpi-value { font-size: 1.8rem; font-weight: 800; margin: 5px 0; color: #ffffff !important; }
    .kpi-meta { font-size: 0.75rem; color: #94a3b8 !important; }
    .semaforo { display: inline-block; padding: 2px 12px; border-radius: 20px; font-size: 0.7rem; font-weight: 700; margin-top: 8px; }
    .semaforo.verde { background: #064e3b; color: #34d399 !important; }
    .semaforo.amarelo { background: #78350f; color: #fbbf24 !important; }
    .semaforo.vermelho { background: #7f1d1d; color: #f87171 !important; }
    .resumo-card { background: #1e293b !important; padding: 20px; border-radius: 10px; border: 1px solid #334155; margin: 15px 0; color: #ffffff !important; }
    .resumo-card * { color: #ffffff !important; }
    .resumo-card h3 { color: #94a3b8 !important; }
    .resumo-card h2 { color: #3b82f6 !important; }
    .login-box { max-width: 400px; margin: 100px auto; padding: 40px; background: #1e293b; border-radius: 16px; }
    .login-title { color: #ffffff; text-align: center; font-size: 1.8rem; margin-bottom: 30px; }
    .badge { display: inline-block; background: #334155; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; }
    .data-card { background: #1e293b !important; border-radius: 10px; padding: 15px; border-left: 4px solid #f59e0b; margin-bottom: 10px; color: #ffffff !important; }
    .data-card * { color: #ffffff !important; }
    .cliente-card { background: #1e293b !important; border-radius: 10px; padding: 15px; border-left: 4px solid #8b5cf6; margin-bottom: 10px; color: #ffffff !important; }
    .cliente-card * { color: #ffffff !important; }
    .user-badge { display: inline-block; background: #3b82f6; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }
    .admin-badge { display: inline-block; background: #8b5cf6; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }
    .card.azul { border-left: 5px solid #3b82f6; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════
# INICIALIZAÇÃO
# ═══════════════════════════════════════════

init_db()
init_usuarios()
# ═══════════════════════════════════════════
# TELA DE LOGIN
# ═══════════════════════════════════════════
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "pagina" not in st.session_state:
    st.session_state.pagina = "login"

if st.session_state.usuario is None:
    if st.session_state.pagina == "login":
        col_centro = st.columns([1, 1, 1])[1]
        with col_centro:
            st.markdown("<div class='login-box'>", unsafe_allow_html=True)
            st.markdown("<div class='login-title'>🧣 Cravate Shop</div>", unsafe_allow_html=True)
            st.markdown("<p style='text-align:center;color:#94a3b8;margin-bottom:25px;'>Faça login para continuar</p>", unsafe_allow_html=True)
            
            email = st.text_input("📧 Email", placeholder="seu@email.com")
            senha = st.text_input("🔒 Senha", type="password", placeholder="Digite sua senha")
            
            if st.button("Entrar", type="primary", use_container_width=True):
                if email and senha:
                    usuario = autenticar(email, senha)
                    if usuario:
                        st.session_state.usuario = usuario
                        st.rerun()
                    else:
                        st.error("Email ou senha inválidos!")
                else:
                    st.warning("Preencha email e senha.")
            
            st.markdown("---")
            if st.button("📝 Criar conta", use_container_width=True):
                st.session_state.pagina = "cadastro"
                st.rerun()
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    elif st.session_state.pagina == "cadastro":
        col_centro = st.columns([1, 1, 1])[1]
        with col_centro:
            st.markdown("<div class='login-box'>", unsafe_allow_html=True)
            st.markdown("<div class='login-title'>📝 Criar Conta</div>", unsafe_allow_html=True)
            
            nome = st.text_input("👤 Nome completo", placeholder="Seu nome")
            email = st.text_input("📧 Email", placeholder="seu@email.com")
            senha1 = st.text_input("🔒 Senha", type="password", placeholder="Mínimo 6 caracteres")
            senha2 = st.text_input("🔒 Confirmar senha", type="password", placeholder="Repita a senha")
            
            if st.button("Cadastrar", type="primary", use_container_width=True):
                if not nome or not email or not senha1:
                    st.warning("Preencha todos os campos!")
                elif senha1 != senha2:
                    st.warning("Senhas não conferem!")
                elif len(senha1) < 6:
                    st.warning("Senha precisa ter no mínimo 6 caracteres!")
                else:
                    if cadastrar_usuario(email, senha1, nome):
                        st.success("Conta criada! Faça login.")
                        st.session_state.pagina = "login"
                        st.rerun()
                    else:
                        st.error("Email já cadastrado!")
            
            if st.button("← Voltar ao login"):
                st.session_state.pagina = "login"
                st.rerun()
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    st.stop()

# ═══════════════════════════════════════════
# SISTEMA PRINCIPAL (logado)
# ═══════════════════════════════════════════
usuario = st.session_state.usuario
admin = usuario["tipo"] == "admin"

# ═══════════════════════════════════════════
# ADMINISTRAÇÃO (só para admin)
# ═══════════════════════════════════════════
if admin:
    st.markdown("---")
    st.markdown("### ⚙️ Administração")

    tab_admin1, tab_admin2 = st.tabs(["👥 Usuários", "🔄 Resetar Sistema"])

    # ─── TAB USUÁRIOS ───
    with tab_admin1:
        df_usuarios = carregar_usuarios()
        for _, row in df_usuarios.iterrows():
            if row['tipo'] == 'admin':
                continue  # Não mostra opção de deletar o admin
            col_u1, col_u2, col_u3, col_u4 = st.columns([2, 2, 2, 1])
            col_u1.write(f"**{row['nome']}**")
            col_u2.write(row['email'])
            col_u3.write(row['tipo'])
            if col_u4.button("🗑️", key=f"del_user_{row['id']}"):
                if deletar_usuario(int(row['id'])):
                    st.success(f"Usuário {row['nome']} deletado!")
                    st.rerun()
                else:
                    st.error("Erro ao deletar usuário.")

        if len(df_usuarios) == 0:
            st.info("Nenhum usuário cadastrado.")

    # ─── TAB RESET ───
    with tab_admin2:
        st.warning("⚠️ Isso vai apagar TODOS os dados do sistema!")
        st.markdown("Será mantido apenas o **admin** e os **produtos** com estoque inicial.")
        st.markdown("Vendas, usuários não-admin e registros serão **permanentemente removidos**.")

        confirmar = st.text_input("Digite 'RESET' para confirmar:", placeholder="RESET")
        if st.button("🔄 Resetar Sistema", type="primary", use_container_width=True):
            if confirmar == "RESET":
                if resetar_sistema():
                    st.success("✅ Sistema resetado com sucesso! Pronto para novo cliente.")
                    st.rerun()
                else:
                    st.error("Erro ao resetar sistema.")
            else:
                st.error("Digite 'RESET' para confirmar.")
# Sidebar
st.sidebar.markdown("## 🧣 Cravate Shop")
st.sidebar.markdown(f"<span class='{'admin-badge' if admin else 'user-badge'}'>{'🔹 ADMIN' if admin else '👤 Cliente'}</span>", unsafe_allow_html=True)
st.sidebar.markdown(f"**{usuario['nome']}**")
st.sidebar.markdown(f"📧 {usuario['email']}")

if st.sidebar.button("🚪 Sair", use_container_width=True):
    st.session_state.usuario = None
    st.rerun()

st.sidebar.markdown("---")

# Carrega dados (se admin, vê tudo; se cliente, vê só o dele)
df_produtos = carregar_produtos()
usuario_id = usuario["id"]
df_vendas = carregar_vendas(usuario_id if not admin else None)

# Resumo do estoque na sidebar
st.sidebar.markdown("### 📦 Resumo do Estoque")
total_itens = int(df_produtos['estoque'].sum())
prod_baixa = df_produtos[df_produtos['estoque'] <= df_produtos['estoque_minimo']]
st.sidebar.markdown(f"**Total em estoque:** {total_itens} itens")
st.sidebar.markdown(f"**Produtos em baixa:** {len(prod_baixa)}")

# Datas na sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 Próximas Datas")
datas_proximas = obter_datas_comemorativas()
proximas_5 = [d for d in datas_proximas if d[2] >= -7][:3]
for nome, data_evento, dias, _ in proximas_5:
    if dias < 0: st.sidebar.markdown(f"✅ **{nome}** — passou há {abs(dias)} dias")
    elif dias == 0: st.sidebar.markdown(f"🔴 **{nome}** — É HOJE!")
    elif dias <= 15: st.sidebar.markdown(f"🟡 **{nome}** — em {dias} dias")
    else: st.sidebar.markdown(f"🟢 **{nome}** — em {dias} dias")

st.sidebar.markdown("---")
st.sidebar.markdown("### Produtos")
for _, row in df_produtos.iterrows():
    st.sidebar.markdown(f"- **{row['nome']}** — R$ {row['preco']:,.2f} — Est: {int(row['estoque'])}un")

# ═══════════════════════════════════════════
# ABAS
# ═══════════════════════════════════════════
if admin:
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Registrar Venda", "📊 Relatórios", "📦 Estoque", "📅 Datas e Clientes", "👥 Usuários"])
else:
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Registrar Venda", "📊 Relatórios", "📦 Estoque", "📅 Datas e Clientes"])

# ─── ABA 1 — REGISTRAR VENDA ───
with tab1:
    col_form, col_hist = st.columns([1, 1.5])
    with col_form:
        st.markdown("### Nova Venda")
        produtos_selecionados = st.multiselect("Produtos", df_produtos['nome'].tolist(), placeholder="Selecione os produtos...")
        if produtos_selecionados:
            itens_venda = []; valor_bruto = 0; qtd_total = 0; pode_vender = True
            st.markdown("**Quantidades:**")
            cols_qtd = st.columns(len(produtos_selecionados))
            for i, prod_nome in enumerate(produtos_selecionados):
                row_p = df_produtos[df_produtos['nome'] == prod_nome].iloc[0]
                max_qtd = int(row_p['estoque'])
                qtd = cols_qtd[i].number_input(prod_nome, min_value=1, value=1, max_value=max_qtd if max_qtd > 0 else 1, key=f"qtd_{prod_nome}", label_visibility="collapsed")
                if qtd > max_qtd: cols_qtd[i].warning(f"Só tem {max_qtd} em estoque!"); pode_vender = False
                subtotal = row_p['preco'] * qtd; valor_bruto += subtotal; qtd_total += qtd
                itens_venda.append(f"{prod_nome} x{qtd} (R$ {subtotal:,.2f})")
            desconto = st.number_input("Desconto (R$)", min_value=0.0, max_value=float(valor_bruto), value=0.0, step=1.0, format="%.2f")
            valor_final = valor_bruto - desconto
            st.markdown(f"""
            <div class="resumo-card">
                <p style="margin:0;">Valor Bruto</p><h3 style="margin:0;">R$ {valor_bruto:,.2f}</h3>
                <p style="margin:10px 0 0 0;">Desconto</p><h3 style="margin:0; color:#ef4444 !important;">- R$ {desconto:,.2f}</h3>
                <hr style="border-color:#334155; margin:15px 0;">
                <p style="margin:0; color:#3b82f6 !important; font-size:1.2rem; font-weight:700;">Total a Pagar</p>
                <h2 style="margin:0; color:#3b82f6 !important;">R$ {valor_final:,.2f}</h2>
            </div>""", unsafe_allow_html=True)
            data_venda = st.date_input("Data da Venda", value=date.today())
            cliente = st.text_input("Nome do Cliente", placeholder="Opcional")
            if st.button("Confirmar Venda", type="primary", use_container_width=True, disabled=not pode_vender):
                for prod_nome in produtos_selecionados:
                    row_p = df_produtos[df_produtos['nome'] == prod_nome].iloc[0]
                    qtd = st.session_state.get(f"qtd_{prod_nome}", 1)
                    baixar_estoque(int(row_p['id']), qtd)
                itens_str = " | ".join(itens_venda)
                registrar_venda(usuario_id, itens_str, qtd_total, valor_bruto, desconto, valor_final, data_venda.strftime("%Y-%m-%d"), cliente if cliente else "Consumidor")
                st.success("Venda registrada! Estoque e mínimo atualizados.")
                st.rerun()
        else:
            st.info("Selecione ao menos um produto.")
    with col_hist:
        st.markdown("### Últimas Vendas")
        if not df_vendas.empty:
            exibir = df_vendas[['data', 'itens', 'valor_bruto', 'desconto', 'valor_final', 'cliente_nome']].head(20)
            exibir.columns = ['Data', 'Itens', 'Valor Bruto', 'Desconto', 'Total', 'Cliente']
            st.dataframe(exibir, use_container_width=True, hide_index=True)
            st.info(f"Soma das últimas 20 vendas: R$ {df_vendas.head(20)['valor_final'].sum():,.2f}")
        else:
            st.info("Nenhuma venda registrada ainda.")

# ─── ABA 2 — RELATÓRIOS ───
with tab2:
    st.markdown("### Dashboard Executivo")
    df_v = df_vendas.copy()
    
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
            qtd_vendas = len(df_filtro)
            qtd_itens = int(df_filtro['quantidade_total'].sum())
            receita = float(df_filtro['valor_final'].sum())
            qtd_clientes = df_filtro['cliente_nome'].nunique()
            ticket = receita / qtd_vendas if qtd_vendas > 0 else 0
            total_desconto = float(df_filtro['desconto'].sum())

            meta_vendas, meta_receita, meta_ticket, meta_clientes, meta_itens = 50, 2000.0, 80.0, 30, 100

            def status(v, m):
                if v >= m: return "verde"
                if v >= m * 0.7: return "amarelo"
                return "vermelho"

            k1, k2, k3, k4, k5 = st.columns(5)
            cards = [
                (k1, "Vendas no Mês", qtd_vendas, meta_vendas),
                (k5, "Itens Vendidos", qtd_itens, meta_itens),
                (k2, "Receita Líquida", f"R$ {receita:,.2f}", f"R$ {meta_receita:,.0f}"),
                (k3, "Ticket Médio", f"R$ {ticket:,.2f}", f"R$ {meta_ticket:,.0f}"),
                (k4, "Clientes", qtd_clientes, meta_clientes),
            ]
            vals = [qtd_vendas, qtd_itens, receita, ticket, qtd_clientes]
            metas = [meta_vendas, meta_itens, meta_receita, meta_ticket, meta_clientes]

            for (col, label, val, meta), v, m in zip(cards, vals, metas):
                sts = status(v, m)
                col.markdown(f"""<div class="card {sts}"><div class="kpi-label">{label}</div><div class="kpi-value">{val}</div><div class="kpi-meta">Meta: {meta}</div><div class="semaforo {sts}">{sts.upper()}</div></div>""", unsafe_allow_html=True)

            st.markdown(f"<p style='color:#94a3b8;'>Desconto total: <strong style='color:#ef4444;'>R$ {total_desconto:,.2f}</strong> | Média de itens por venda: <strong>{qtd_itens/qtd_vendas:.1f}</strong></p>", unsafe_allow_html=True)

            st.markdown("### 📈 Receita Diária")
            df_dia = df_filtro.groupby('data')['valor_final'].sum().reset_index()
            chart = alt.Chart(df_dia).mark_bar(color='#3b82f6').encode(
                x=alt.X('data:T', title='Data'), y=alt.Y('valor_final:Q', title='Receita (R$)'), tooltip=['data', 'valor_final']
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)

            st.markdown("### 💡 Insights")
            st.markdown(f"""<div class="card verde"><strong>🔍 Resumo</strong><br><br>• <strong>{qtd_vendas}</strong> vendas ({qtd_itens} itens)<br>• <strong>{qtd_clientes}</strong> clientes<br>• Receita: <strong>R$ {receita:,.2f}</strong> | Descontos: <strong>R$ {total_desconto:,.2f}</strong><br>• Ticket médio: <strong>R$ {ticket:,.2f}</strong></div>""", unsafe_allow_html=True)
        else:
            st.info("Nenhuma venda no período.")
    else:
        st.info("Nenhuma venda registrada.")

# ─── ABA 3 — ESTOQUE ───
with tab3:
    st.markdown("### 📦 Controle de Estoque")
    df_produtos = carregar_produtos()

    produtos_criticos = df_produtos[df_produtos['estoque'] == 0]
    produtos_baixa = df_produtos[df_produtos['estoque'] <= df_produtos['estoque_minimo']]
    produtos_ok = df_produtos[df_produtos['estoque'] > df_produtos['estoque_minimo']]

    # Valor total investido em estoque
    valor_investido = (df_produtos['preco'] * df_produtos['estoque']).sum()

    col_rec1, col_rec2, col_rec3, col_rec4 = st.columns(4)

    col_rec1.markdown(f"""<div class="card vermelho"><div class="kpi-label">🔴 Em Falta</div><div class="kpi-value">{len(produtos_criticos)}</div><div class="kpi-meta">Estoque zerado</div></div>""", unsafe_allow_html=True)

    # Nomes dos produtos em baixa
    nomes_baixa = ", ".join(produtos_baixa['nome'].tolist()) if len(produtos_baixa) > 0 else "—"
    col_rec2.markdown(f"""<div class="card amarelo"><div class="kpi-label">🟡 Em Baixa</div><div class="kpi-value">{len(produtos_baixa)}</div><div class="kpi-meta">Abaixo do mínimo</div><div style="font-size:0.7rem;color:#fbbf24;margin-top:4px;">{nomes_baixa}</div></div>""", unsafe_allow_html=True)

    col_rec3.markdown(f"""<div class="card verde"><div class="kpi-label">🟢 Estoque OK</div><div class="kpi-value">{len(produtos_ok)}</div><div class="kpi-meta">Dentro do esperado</div></div>""", unsafe_allow_html=True)

    col_rec4.markdown(f"""<div class="card azul"><div class="kpi-label">💰 Valor em Estoque</div><div class="kpi-value" style="font-size:1.1rem;">R$ {valor_investido:,.2f}</div><div class="kpi-meta">Total investido</div></div>""", unsafe_allow_html=True)

    # Botão recalcular abaixo dos cards
    st.markdown("")
    if st.button("🔄 Recalcular Mínimos", use_container_width=True):
        atualizar_estoque_minimo_automatico()
        st.success("Mínimos recalculados!")
        st.rerun()

    st.markdown("### Produtos")
    for _, row in df_produtos.iterrows():
        estoque = int(row['estoque']); minimo = int(row['estoque_minimo']); preco = float(row['preco'])
        if estoque == 0: cor = "vermelho"; status_text = "🔴 EM FALTA"
        elif estoque <= minimo: cor = "amarelo"; qtd_repor = minimo * 2 - estoque; status_text = f"🟡 Compre {qtd_repor}un"
        else: cor = "verde"; status_text = "🟢 OK"
        with st.container():
            st.markdown(f"""<div class="card {cor}"><div style="display:flex;justify-content:space-between;align-items:center;"><div><strong>{row['nome']}</strong><span class="badge" style="margin-left:10px;">{row['categoria']}</span></div><div>Preço: <strong style="color:#3b82f6;">R$ {preco:,.2f}</strong></div></div><div style="display:flex;justify-content:space-between;margin-top:10px;"><div><span>Estoque:</span><span style="font-size:1.3rem;font-weight:800;margin-left:8px;color:{'#f87171' if estoque <= minimo else '#34d399'}">{estoque} un</span><span style="font-size:0.75rem;margin-left:10px;">Mín: {minimo}un</span></div><span style="font-size:0.8rem;color:#f87171;font-weight:600;">{status_text}</span></div></div>""", unsafe_allow_html=True)
            with st.expander(f"✏️ Editar {row['nome']}"):
                col_ed1, col_ed2, col_ed3 = st.columns(3)
                nova_qtd = col_ed1.number_input("Qtd", min_value=0, value=estoque, step=1, key=f"edit_est_{row['id']}", label_visibility="collapsed")
                novo_min = col_ed2.number_input("Mín", min_value=1, value=minimo, step=1, key=f"edit_min_{row['id']}", label_visibility="collapsed")
                novo_preco = col_ed3.number_input("Preço", min_value=0.01, value=preco, step=1.0, format="%.2f", key=f"edit_prec_{row['id']}", label_visibility="collapsed")
                if st.button(f"Salvar", key=f"btn_{row['id']}", use_container_width=True):
                    editar_produto(int(row['id']), nova_qtd, novo_min, novo_preco)
                    st.success("Atualizado!")
                    st.rerun()

    produtos_baixa = df_produtos[df_produtos['estoque'] <= df_produtos['estoque_minimo']]
    if len(produtos_baixa) > 0:
        st.markdown("### 🛒 Sugestão de Compra")
        for _, row in produtos_baixa.iterrows():
            est = int(row['estoque']); min_ = int(row['estoque_minimo'])
            sug = min_ * 3 - est
            st.markdown(f"""<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #334155;color:#fff;"><span><strong>{row['nome']}</strong> ({row['categoria']})</span><span>Est: {est}un | Mín: {min_}un | <strong style="color:#fbbf24;">Comprar: {sug}un</strong></span></div>""", unsafe_allow_html=True)
# ─── ABA 4 — DATAS E CLIENTES ───
with tab4:
    st.markdown("### 📅 Calendário Comercial")
    datas = obter_datas_comemorativas()
    for nome, data_evento, dias, sugestao in datas:
        if dias < 0: emoji, label = "✅", f"passou há {abs(dias)} dias"
        elif dias == 0: emoji, label = "🔴🔴", "é hoje!"
        elif dias <= 7: emoji, label = "🟡", f"em {dias} dia(s)"
        elif dias <= 30: emoji, label = "🟢", f"em {dias} dia(s)"
        else: emoji, label = "🔵", f"em {dias} dia(s)"
        st.markdown(f"""<div class="data-card"><div style="display:flex;justify-content:space-between;"><div><strong>{emoji} {nome}</strong> — {data_evento.strftime('%d/%m/%Y')}</div><div style="color:#fbbf24;font-weight:700;">{label}</div></div><div style="margin-top:5px;font-size:0.85rem;color:#94a3b8;">💡 {sugestao}</div></div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 👥 Insights de Clientes")
    if not df_vendas.empty:
        df_vc = df_vendas.copy()
        df_vc['data'] = pd.to_datetime(df_vc['data'])
        clientes = df_vc.groupby('cliente_nome').agg(Compras=('id','count'), Itens=('quantidade_total','sum'), Total_Gasto=('valor_final','sum')).sort_values('Total_Gasto', ascending=False).reset_index()
        st.dataframe(clientes, use_container_width=True, hide_index=True)
        if not clientes.empty:
            top = clientes.iloc[0]
            st.markdown(f"""<div class="cliente-card"><strong>🏆 Destaque: {top['cliente_nome']}</strong> — {int(top['Compras'])} compras, R$ {top['Total_Gasto']:,.2f}</div>""", unsafe_allow_html=True)

        hoje = date.today()
        ultima = df_vc.groupby('cliente_nome')['data'].max().reset_index()
        ultima['dias'] = (pd.to_datetime(hoje) - pd.to_datetime(ultima['data'])).dt.days
        inativos = ultima[ultima['dias'] > 7].sort_values('dias', ascending=False)
        if not inativos.empty:
            st.markdown("#### ⚠️ Clientes Inativos")
            for _, r in inativos.iterrows():
                st.markdown(f"""<div class="card amarelo" style="padding:12px;"><strong>{r['cliente_nome']}</strong> — sem comprar há {int(r['dias'])} dias</div>""", unsafe_allow_html=True)
    else:
        st.info("Nenhum cliente registrado.")

# ─── ABA 5 — USUÁRIOS (só admin) ───
if admin:
    with tab5:
        st.markdown("### 👥 Gerenciar Usuários")
        
        col_u1, col_u2 = st.columns([2, 1])
        with col_u1:
            st.markdown("**Usuários cadastrados:**")
            df_usuarios = carregar_usuarios()
            if not df_usuarios.empty:
                df_exibir = df_usuarios.copy()
                df_exibir['tipo'] = df_exibir['tipo'].apply(lambda x: "🔹 Admin" if x == "admin" else "👤 Cliente")
                st.dataframe(df_exibir, use_container_width=True, hide_index=True)
        
        with col_u2:
            st.markdown("**Cadastrar novo usuário:**")
            with st.form("novo_usuario"):
                nome_novo = st.text_input("Nome", placeholder="Nome completo")
                email_novo = st.text_input("Email", placeholder="email@cliente.com")
                senha_novo = st.text_input("Senha", type="password", placeholder="Mín 6 caracteres")
                tipo_novo = st.selectbox("Tipo", ["cliente", "admin"])
                if st.form_submit_button("Cadastrar", type="primary", use_container_width=True):
                    if nome_novo and email_novo and senha_novo:
                        if cadastrar_usuario(email_novo, senha_novo, nome_novo, tipo_novo):
                            st.success(f"Usuário {nome_novo} cadastrado!")
                            st.rerun()
                        else:
                            st.error("Email já existe!")
                    else:
                        st.warning("Preencha todos os campos!")
        
        # Totais
        st.markdown("---")
        st.markdown("### 📊 Estatísticas")
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.markdown(f"""<div class="card azul"><div class="kpi-label">Total de Usuários</div><div class="kpi-value">{len(df_usuarios)}</div></div>""", unsafe_allow_html=True)
        qtd_admin = len(df_usuarios[df_usuarios['tipo'] == 'admin'])
        qtd_clientes = len(df_usuarios[df_usuarios['tipo'] == 'cliente'])
        col_s2.markdown(f"""<div class="card roxo"><div class="kpi-label">Administradores</div><div class="kpi-value">{qtd_admin}</div></div>""", unsafe_allow_html=True)
        col_s3.markdown(f"""<div class="card verde"><div class="kpi-label">Clientes</div><div class="kpi-value">{qtd_clientes}</div></div>""", unsafe_allow_html=True)