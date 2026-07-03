import psycopg
import time

def conecta(db_host, db_port, db_name, db_user, db_pass):
    tempo_inicio = time.time()
    conexao = None
    try:
        conexao = psycopg.connect(f"host={db_host} port={db_port} dbname={db_name} user={db_user} password={db_pass}")
        print(f"Tempo para conexão: {time.time() - tempo_inicio:.3f} seg")
        return conexao
    except (psycopg.DatabaseError, Exception) as erro:
        print("Não foi possível conectar-se.", erro)
    
    return None

def desconecta(conexao):
    try:
        conexao.close()
        print("Conexão encerrada.")
    except (psycopg.DatabaseError, Exception) as erro:
        print("Não foi possível encerrar a conexão.", erro)

def desconecta_cursor(cursor):
    try:
        cursor.close()
    except (psycopg.DatabaseError, Exception) as erro:
        print("Erro ao tentar desconectar o cursor.", erro)