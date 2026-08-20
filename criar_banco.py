import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Configurações de Conexão
DB_HOST = "localhost"
DB_PORT = "5432"
DB_USER = "postgres"
DB_PASSWORD = "123456"  # <--- Coloque a senha definida na instalação!


def criar_banco():
    try:
        # Conecta no banco padrão 'postgres'
        con = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname="postgres",
        )
        con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = con.cursor()

        # Verifica se o banco gestao_escolar já existe
        cursor.execute(
            "SELECT 1 FROM pg_catalog.pg_database WHERE datname ="
            " 'gestao_escolar'"
        )
        existe = cursor.fetchone()

        if not existe:
            cursor.execute("CREATE DATABASE gestao_escolar;")
            print("✅ Banco de dados 'gestao_escolar' criado com sucesso!")
        else:
            print("ℹ️ O banco 'gestao_escolar' já existe.")

        cursor.close()
        con.close()
    except Exception as e:
        print(f"❌ Erro ao conectar/criar banco: {e}")


if __name__ == "__main__":
    criar_banco()