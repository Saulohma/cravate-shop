"""Migra dados do SQLite local para Neon PostgreSQL"""
import sqlite3
import pandas as pd
from sqlalchemy import create_engine, text
import os

# Conexões
SQLITE_PATH = "cravate_shop.db"
NEON_STRING = os.environ.get("NEON_CONNECTION_STRING") or input("Cole sua Neon connection string: ")

# Conecta SQLite
sqlite_conn = sqlite3.connect(SQLITE_PATH)

# Conecta Neon
neon_engine = create_engine(NEON_STRING)

print("🔄 Migrando produtos...")
df_produtos = pd.read_sql_query("SELECT * FROM produtos", sqlite_conn)
if not df_produtos.empty:
    df_produtos.to_sql("produtos", neon_engine, if_exists="append", index=False)
    print(f"  ✅ {len(df_produtos)} produtos migrados")

print("🔄 Migrando vendas...")
df_vendas = pd.read_sql_query("SELECT * FROM vendas", sqlite_conn)
if not df_vendas.empty:
    # Adiciona usuario_id = 1 (admin) para vendas antigas
    df_vendas["usuario_id"] = 1
    df_vendas.to_sql("vendas", neon_engine, if_exists="append", index=False)
    print(f"  ✅ {len(df_vendas)} vendas migradas")

print("🎉 Migração concluída!")
sqlite_conn.close()