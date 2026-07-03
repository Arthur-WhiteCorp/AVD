import sys
import psycopg
import time
import argparse
from db import * #Importa utilidades do arquivo db.py

def parse_args():
    parser= argparse.ArgumentParser()
    parser.add_argument('--db-host')
    parser.add_argument('--db-port', type=int)
    parser.add_argument('--db-name')
    parser.add_argument('--db-user')
    parser.add_argument('--db-pass')
    parser.add_argument('--input')
    return parser.parse_args()

def criaTabelas(cur, conexao):
    tempo_inicio = time.time()
    #Criando tabelas de acordo com o esquema

    comando = [
        """CREATE TABLE PRODUCT(
        Pid INT PRIMARY KEY,
        ASIN CHAR(10) NOT NULL UNIQUE
        );
        """,
        """CREATE TABLE PRODUCT_INFO(
        Pid INT PRIMARY KEY REFERENCES PRODUCT(Pid) ON DELETE CASCADE,
        title VARCHAR(500),
        p_group VARCHAR(12),
        salesrank INT,
        p_similar INT,
        categories INT,
        reviews INT,
        downloads INT,
        avg_rating FLOAT
        );
        """,
        """CREATE TABLE SIMILAR_PRODUCT(
        Pid INT REFERENCES PRODUCT(Pid) ON DELETE CASCADE,
        ASIN_SIM CHAR(10),
        PRIMARY KEY (Pid, ASIN_SIM)
        );
        """,
        """CREATE TABLE CATEGORY(
        cat_id INT PRIMARY KEY,
        cat_nome VARCHAR(100),
        pcat_id INT REFERENCES CATEGORY(cat_id)
        );
        """,
        """CREATE TABLE PRODUCT_CAT(
        Pid INT REFERENCES PRODUCT(Pid) ON DELETE CASCADE,
        id_final_cat INT REFERENCES CATEGORY(cat_id) ON DELETE CASCADE,
        PRIMARY KEY (Pid, id_final_cat)
        );
        """,
        """CREATE TABLE REVIEW(
        rev_id INT,
        Pid INT REFERENCES PRODUCT(Pid) ON DELETE CASCADE,
        date DATE,
        cutomer VARCHAR(14),
        rating SMALLINT,
        votes INT,
        helpful INT,
        PRIMARY KEY (rev_id, Pid),
        CHECK (rating > 0 AND rating <= 5),
        CHECK (helpful <= votes)
        );
        """
    ]
    try:
        for com in comando:
            cur.execute(com)
        conexao.commit()
        print(f"Tempo para criar o esquema: {time.time() - tempo_inicio:.3f} seg")
        return 0
    except (psycopg.DatabaseError, Exception) as erro:
        print("Não foi possível criar o esquema.", erro)
    return 1

def lerEntrada(arq_i):
    tempo_inicio = time.time()
    linhas = ''
    try:
        with open(arq_i, "r") as arq_i:
            linhas = arq_i.readlines()
        print(f"Tempo para ler o arquivo de entrada: {time.time() - tempo_inicio:.3f} seg")
    except (psycopg.DatabaseError, Exception) as erro:
        print("Não foi possível ler o arquivo.", erro)
    return linhas

def copy_csv(cur, conexao, tabela, inserts, arq, cats_lidas):
    nome_arq = arq
    with open(nome_arq, 'w') as arq:
        for i in inserts:
            if tabela != "CATEGORY":
                arq.write(i)
            elif i not in cats_lidas:
                arq.write(i)
                cats_lidas.add(i)
    try:
        with open(nome_arq, 'r') as arq:
            with cur.copy(f"COPY {tabela} FROM STDIN WITH (FORMAT csv, NULL 'NULL');") as copy:
                copy.write(arq.read())
        conexao.commit()
    except (psycopg.DatabaseError, Exception) as erro:
        print(f"Não foi possível preencher relação {tabela}.", erro)
        desconecta_cursor(cursor)
        desconecta(conexao)
        sys.exit(1)

def povoaRelacoes(cur, conexao, linhas):
    tempo_inicio = time.time()
    nlinhas = 0
    csv_produto = []
    csv_prodinfo = []
    csv_similar = []
    csv_category = []
    csv_prodcat = []
    csv_review = []
    cats_lidas = set()
    try:
        for l in linhas:
            linha = l.split()
            if "Id:   " in l:
                id = linha[1]
            elif "ASIN:" in l:
                asin = linha[1]
                #A inserir
                csv_produto += [f"{id},{asin}\n"]
            elif "title:" in l:
                titulo = l.split(": ", maxsplit=1)[1]
                titulo = titulo.strip('\n')
                titulo = titulo.replace('"', '""')
                titulo = titulo.replace(',', '","')
            elif "group:" in l:
                group = linha[1]
            elif "salesrank:" in l:
                sales = linha[1]
            elif "similar:" in l:
                similar = linha[1]
                for sim in linha[2:]:
                    asin_sim = sim.strip('\n')
                    #A inserir
                    csv_similar += [f"{id},{asin_sim}\n"]
            elif "categories:" in l:
                categoria = linha[1]
            elif '|' in l and linha[0][0] == '|': #Lista de categorias
                linha_cat = l.split('|')
                pcat_id = "NULL"
                for cat in linha_cat[1:]:
                    cat = cat.strip('\n')
                    if cat.index(']') == len(cat)-1:
                        cat_id = cat[(cat.index('[')+1):(cat.index(']'))]
                        cat_nome = cat[:(cat.index('['))]
                    else:
                        cat_id = cat[(cat.index('[')+1):(len(cat)-1)]
                        i_cochete = cat_id.index('[')
                        cat_id = cat_id[i_cochete+1:]
                        i_cochete += cat.index('[')
                        cat_nome = cat[:i_cochete+1]
                    cat_nome = cat_nome.replace(',', '","')
                    #A inserir
                    csv_category += [f"{cat_id},{cat_nome},{pcat_id}\n"]
                    pcat_id = cat_id
                #A inserir
                csv_prodcat += [f"{id},{cat_id}\n"]
            elif "reviews:" in l:
                total = l.split(": ")[2].split()[0]
                downloads = l.split(": ")[3].split()[0]
                avg = l.split(": ")[4]
                #A inserir
                csv_prodinfo += [f"{id},{titulo},{group},{sales},{similar},{categoria},{total},{downloads},{avg}"]
                rev_id = 1
            elif "cutomer:" in l:
                data = linha[0]
                cutomer = linha[2]
                rating = linha[4]
                votes = linha[6]
                helpful = linha[8]
                #A inserir
                csv_review += [f"{rev_id},{id},{data},{cutomer},{rating},{votes},{helpful}\n"]
                rev_id += 1
            nlinhas += 1
            if nlinhas % 1000000 == 0:
                print(f"{nlinhas} linhas processadas.")
                copy_csv(cur, conexao, "PRODUCT", csv_produto, "/app/out/tabela_product.csv", cats_lidas)
                csv_produto = []
                copy_csv(cur, conexao, "PRODUCT_INFO", csv_prodinfo, "/app/out/tabela_product_info.csv", cats_lidas)
                csv_prodinfo = []
                copy_csv(cur, conexao, "SIMILAR_PRODUCT", csv_similar, "/app/out/tabela_similar_product.csv", cats_lidas)
                csv_similar = []
                copy_csv(cur, conexao, "CATEGORY", csv_category, "/app/out/tabela_category.csv", cats_lidas)
                csv_category = []
                copy_csv(cur, conexao, "PRODUCT_CAT", csv_prodcat, "/app/out/tabela_prodcat.csv", cats_lidas)
                csv_prodcat = []
                copy_csv(cur, conexao, "REVIEW", csv_review, "/app/out/tabela_review.csv", cats_lidas)
                csv_review = []
            
        print(f"{nlinhas} linhas processadas.")
        copy_csv(cur, conexao, "PRODUCT", csv_produto, "/app/out/tabela_product.csv", cats_lidas)
        copy_csv(cur, conexao, "PRODUCT_INFO", csv_prodinfo, "/app/out/tabela_product_info.csv", cats_lidas)
        copy_csv(cur, conexao, "SIMILAR_PRODUCT", csv_similar, "/app/out/tabela_similar_product.csv", cats_lidas)
        copy_csv(cur, conexao, "CATEGORY", csv_category, "/app/out/tabela_category.csv", cats_lidas)
        copy_csv(cur, conexao, "PRODUCT_CAT", csv_prodcat, "/app/out/tabela_prodcat.csv", cats_lidas)
        copy_csv(cur, conexao, "REVIEW", csv_review, "/app/out/tabela_review.csv", cats_lidas)

        conexao.commit()
        print(f"Tempo para povoar relações: {time.time() - tempo_inicio:.3f} seg")
        return 0
    except (psycopg.DatabaseError, Exception) as erro:
        print("Não foi possível povoar relações.", erro)
    return 1

#Estabelece a conexão com o postgreSQL
args = parse_args()

if args.input:
    arq = args.input
else:
    print("Falta arquivo de entrada.")
    sys.exit(1)

conexao= conecta(args.db_host, args.db_port, args.db_name, args.db_user, args.db_pass)
if conexao == None:
    sys.exit(1)
cursor = conexao.cursor()

#Criando o esquema e povoando
status = criaTabelas(cursor, conexao)
if status == 0:
    entrada = lerEntrada(arq)
    status = povoaRelacoes(cursor, conexao, entrada)

#Encerra conexão
desconecta_cursor(cursor)
desconecta(conexao)
if status != 0:
    sys.exit(1)
sys.exit(0)