import sys
import psycopg
import time
import argparse
from db import * #importando de db.py
import json
import csv
from pathlib import Path
from datetime import datetime
import pandas as pd
import statsmodels.formula.api as smf
from pyDOE3 import ff2n
import numpy as np
from scipy.stats import hmean

def parse_args():
    parser= argparse.ArgumentParser()
    parser.add_argument('--db-host')
    parser.add_argument('--db-port', type=int)
    parser.add_argument('--db-name')
    parser.add_argument('--db-user')
    parser.add_argument('--db-pass')
    parser.add_argument('--output')  #opcional, se quiser salvar resultados
    parser.add_argument('--repeticoes',  type=int)
    return parser.parse_args()

def guardaOutput(cur, conexao, consulta, arq):
    try:
        with open(arq, 'wb') as arq:
            with cur.copy(f"COPY ({consulta}) TO STDOUT WITH (FORMAT csv, NULL 'NULL');") as copy:
                for tuplas in copy:
                    arq.write(tuplas)
        print("Resultado da consulta salvo.")
        return 0
    except (psycopg.DatabaseError, Exception) as erro:
        print("Não foi possível salvar resultado da consulta.", erro)
        desconecta_cursor(cur)
        desconecta(conexao)
        sys.exit(1)


import json
import time
import csv
import platform
import socket
import getpass
from pathlib import Path
from datetime import datetime


class KFactorial:
    def __init__(self,
                 cursor,
                 queries,
                 tabela_sinais,
                 config_experimento):
        """
        :param queries: queries brutas
        :param tabela_sinais: tabela de sinais do experimento
        :param config_experimento: dicionário contendo configurações
        """
        self.queries_base = queries
        self.queries_selecionadas = []
        self.queries_ordenadas = []
        self.tabela_sinais = tabela_sinais
        self.config_experimento = config_experimento
        self.num_queries = 0
        self.warmup = 0

    def configura_quantidade(self, valor):
        """
        Configura a quantidade de queries para o experimento.
        valor = 1: usa todas as queries
        valor = -1: usa metade das queries do início + metade de outra posição
        """
        if valor == 1:
            self.num_queries = self.config_experimento["C"][valor]
            self.queries_selecionadas = self.queries_base.copy()
        
        elif valor == -1:
            self.num_queries = self.config_experimento["C"][valor]
            metade = self.num_queries // 2
            
            # Seleciona metade do início
            self.queries_selecionadas = self.queries_base[:metade].copy()
            
            # Seleciona metade a partir da posição 50 (ou usa um offset diferente)
            offset = min(50, len(self.queries_base) - metade)  # Evita index out of range
            self.queries_selecionadas.extend(self.queries_base[offset:offset + metade])
            
            # Se num_queries for ímpar, adiciona mais um elemento
            if self.num_queries % 2 != 0 and len(self.queries_selecionadas) < self.num_queries:
                self.queries_selecionadas.append(self.queries_base[-1])
        
        else:
            print("[ERRO] Campo 'C' configurado erroneamente")

    def configura_ordem(self, valor):
        """
        Configura a ordem de execução das queries.
        valor = 1: mantém ordem original
        valor = -1: intercala blocos de 5 da primeira e segunda metade
        """
        # SEMPRE reiniciar a lista de queries ordenadas
        self.queries_ordenadas = []
        
        if valor == 1:
            self.queries_ordenadas = self.queries_selecionadas.copy()
        
        elif valor == -1:
            # Se não houver queries selecionadas, não faz nada
            if not self.queries_selecionadas:
                print("[AVISO] Nenhuma query selecionada para ordenar")
                return
            
            ponto_corte = len(self.queries_selecionadas) // 2
            tamanho_bloco = 5
            quantidade_blocos = len(self.queries_selecionadas) // (tamanho_bloco * 2)
            
            for i in range(quantidade_blocos):
                # Bloco da primeira metade
                inicio_par = i * tamanho_bloco
                fim_par = inicio_par + tamanho_bloco
                self.queries_ordenadas.extend(
                    self.queries_selecionadas[inicio_par:fim_par]
                )
                
                # Bloco da segunda metade
                inicio_impar = ponto_corte + (i * tamanho_bloco)
                fim_impar = inicio_impar + tamanho_bloco
                self.queries_ordenadas.extend(
                    self.queries_selecionadas[inicio_impar:fim_impar]
                )
            
            # Adiciona queries restantes (se houver)
            # Primeira metade restante
            resto_inicio = quantidade_blocos * tamanho_bloco
            if resto_inicio < ponto_corte:
                self.queries_ordenadas.extend(
                    self.queries_selecionadas[resto_inicio:ponto_corte]
                )
            
            # Segunda metade restante
            resto_inicio = ponto_corte + (quantidade_blocos * tamanho_bloco)
            if resto_inicio < len(self.queries_selecionadas):
                self.queries_ordenadas.extend(
                    self.queries_selecionadas[resto_inicio:]
                )
        
        else:
            print("[ERRO] Campo 'A' configurado erroneamente")
        
    def configura_warmup(self, valor): # Configure por último
        if valor == 1 or valor == -1:
            self.warmup = self.config_experimento["B"][valor]
        else:
            print("[ERRO] Campo 'B' configurado erroneamente")
        

     
class ColetorBenchmarkingBD:
    """
    Coletor de baseline para estudos de Avaliação de Desempenho (AVD).

    Objetivos:
    - Registrar dados brutos individuais
    - Permitir replicabilidade
    - Produzir metadados do experimento
    - Separar warmup de coleta oficial
    - Registrar cache frio/quente
    - Registrar erros sem contaminar estatística
    """

    def __init__(
        self,
        sistema_id,
        arquivo_queries="queries.json",
        nome_arquivo="benchmarking_amazon_2006.csv",
        dataset="amazon_2006",
        warmup=5,
    ):
        """
        :param sistema_id:
            Nome do sistema avaliado.
            Ex: postgres, mongodb, neo4j

        :param arquivo_queries:
            Arquivo JSON contendo queries.

        :param nome_arquivo:
            Nome do CSV de saída.

        :param dataset:
            Nome da carga/dataset.

        :param warmup:
            Número de execuções de aquecimento.
        """

        self.sistema_id = sistema_id
        self.dataset = dataset
        self.warmup = warmup

        diretorio_script = Path(__file__).parent.absolute()

        self.caminho_queries = diretorio_script / arquivo_queries

        self.pasta_saida = diretorio_script / "out"
        self.pasta_saida.mkdir(parents=True, exist_ok=True)

        self.caminho_saida = self.pasta_saida / nome_arquivo

        self.caminho_metadados = (
            self.pasta_saida /
            f"metadata_{self.sistema_id}.json"
        )

        self.caminho_planos = (
            self.pasta_saida /
            f"planos_{self.sistema_id}.txt"
        )

        self.queries_json = self._carregar_queries()

    # =========================================================
    # CARREGAMENTO DE QUERIES
    # =========================================================

    def _carregar_queries(self):
        """Carrega queries do JSON."""

        if not self.caminho_queries.exists():
            print(f"[ERRO] Arquivo não encontrado:")
            print(self.caminho_queries)
            return []

        try:
            with open(self.caminho_queries, "r", encoding="utf-8") as f:
                dados = json.load(f)

            print(f"[OK] {len(dados)} queries carregadas.")
            return dados

        except Exception as e:
            print(f"[ERRO] Falha ao carregar queries:")
            print(str(e))
            return []

    # =========================================================
    # METADADOS
    # =========================================================

    def salvar_metadados(
        self,
        db_versao="desconhecida",
        observacoes=""
    ):
        """
        Salva metadados do experimento.
        """

        metadados = {
            "timestamp_inicio": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            "sistema_avaliado": self.sistema_id,
            "versao_banco": db_versao,

            "dataset": self.dataset,

            "total_queries": len(self.queries_json),

            "warmup_execucoes": self.warmup,

            "sistema_operacional": platform.platform(),

            "hostname": socket.gethostname(),

            "usuario_execucao": getpass.getuser(),

            "python_versao": platform.python_version(),

            "processador": platform.processor(),

            "arquitetura": platform.machine(),

            "observacoes": observacoes
        }

        with open(
            self.caminho_metadados,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                metadados,
                f,
                indent=4,
                ensure_ascii=False
            )

        print("[OK] Metadados salvos.")

    # =========================================================
    # CSV
    # =========================================================

    def _criar_csv_se_necessario(self):
        """Cria/Reseta o CSV com cabeçalho apenas na primeira execução do objeto."""
        
        if getattr(self, '_csv_inicializado', False):
            return

        with open(
            self.caminho_saida,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:
            escritor = csv.writer(f, delimiter=';')
            escritor.writerow([
                "run", "timestamp", "sistema", "query_id", "carga", 
                "categoria", "metrica", "unidade", "valor", "tempo", 
                "num_tuplas", "observacao"
            ])
        
        self._csv_inicializado = True

    def registrar(
        self,
        run,
        query_id,
        titulo,
        categoria,
        tempo_ms,
        num_tuplas,
        obs
    ):
        """
        Registra UMA execução individual.
        """

        tp_ms = num_tuplas / tempo_ms if tempo_ms > 0 else 0

        self._criar_csv_se_necessario()

        with open(
            self.caminho_saida,
            "a",
            newline="",
            encoding="utf-8"
        ) as f:

            escritor = csv.writer(f, delimiter=';')

            escritor.writerow([
                run,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.sistema_id,
                query_id,
                titulo,
                categoria,
                "tuplas por milissegundos",
                "tp/ms",
                tp_ms,
                f"{tempo_ms:.4f}",
                num_tuplas,
                obs,
            ])

    # =========================================================
    # WARMUP
    # =========================================================

    def salvar_planos_execucao(self, cursor):
        """
        Salva em TXT:
        - plano de execução
        - índices utilizados
        - buffers/cache

        Apenas uma vez por consulta.
        """

        print("\n[PLANOS] Coletando planos de execução...")

        with open(
            self.caminho_planos,
            "w",
            encoding="utf-8"
        ) as arquivo:

            arquivo.write("=" * 100 + "\n")
            arquivo.write("PLANOS DE EXECUÇÃO DAS CONSULTAS\n")
            arquivo.write("=" * 100 + "\n\n")

            for item in self.queries_json:

                query_id = item.get("id")
                titulo = item.get("titulo", "sem_titulo")
                categoria = item.get("categoria", "desconhecida")
                sql = item.get("sql")

                if not sql:
                    continue

                try:

                    explain_sql = f"""
                    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                    {sql}
                    """

                    cursor.execute(explain_sql)

                    plano = cursor.fetchall()

                    plano_texto = "\n".join(
                        linha[0]
                        for linha in plano
                    )

                    # -----------------------------------------
                    # Detectar índices
                    # -----------------------------------------

                    indices_detectados = []

                    for linha in plano_texto.splitlines():

                        if "Index Scan" in linha:
                            indices_detectados.append(
                                linha.strip()
                            )

                        elif "Bitmap Index Scan" in linha:
                            indices_detectados.append(
                                linha.strip()
                            )

                    if not indices_detectados:
                        indices_detectados.append(
                            "Nenhum índice detectado."
                        )

                    # -----------------------------------------
                    # Detectar buffers/cache
                    # -----------------------------------------

                    buffers = []

                    for linha in plano_texto.splitlines():

                        if "Buffers:" in linha:
                            buffers.append(
                                linha.strip()
                            )

                    if not buffers:
                        buffers.append(
                            "Informações de buffer não encontradas."
                        )

                    # -----------------------------------------
                    # Escrever no TXT
                    # -----------------------------------------

                    arquivo.write("=" * 100 + "\n")
                    arquivo.write(f"QUERY ID : {query_id}\n")
                    arquivo.write(f"TÍTULO   : {titulo}\n")
                    arquivo.write(f"CATEGORIA: {categoria}\n")
                    arquivo.write("=" * 100 + "\n\n")

                    arquivo.write("SQL:\n")
                    arquivo.write("-" * 100 + "\n")
                    arquivo.write(sql.strip())
                    arquivo.write("\n\n")

                    arquivo.write("PLANO DE EXECUÇÃO:\n")
                    arquivo.write("-" * 100 + "\n")
                    arquivo.write(plano_texto)
                    arquivo.write("\n\n")

                    arquivo.write("ÍNDICES DETECTADOS:\n")
                    arquivo.write("-" * 100 + "\n")

                    for idx in indices_detectados:
                        arquivo.write(idx + "\n")

                    arquivo.write("\n")

                    arquivo.write("CACHE / BUFFERS:\n")
                    arquivo.write("-" * 100 + "\n")

                    for b in buffers:
                        arquivo.write(b + "\n")

                    arquivo.write("\n\n")

                    print(
                        f"[OK] Plano da Query {query_id} salvo."
                    )

                except Exception as e:

                    arquivo.write("=" * 100 + "\n")
                    arquivo.write(
                        f"ERRO NA QUERY {query_id}\n"
                    )
                    arquivo.write("=" * 100 + "\n")
                    arquivo.write(str(e))
                    arquivo.write("\n\n")

                    print(
                        f"[ERRO] Query {query_id}: {e}"
                    )

        print("[OK] Planos salvos.")

    def executar_warmup(self, cursor):
        """
        Executa warmup sem registrar resultados.
        """

        if self.warmup <= 0:
            return

        print(f"\n[WARMUP] Executando {self.warmup} warmups...")

        # -----------------------------------------------------
        # Salvar planos UMA vez
        # -----------------------------------------------------

        #self.salvar_planos_execucao(cursor)

        for item in self.queries_json:

            sql = item.get("sql")

            if not sql:
                continue

            for _ in range(self.warmup):

                try:
                    cursor.execute(sql)

                    if cursor.description:
                        cursor.fetchall()

                except Exception:
                    pass

        print("[OK] Warmup finalizado.")

    # =========================================================
    # EXECUÇÃO PRINCIPAL
    # =========================================================

    def executar_experimento(
        self,
        cursor,
        repeticoes=40
    ):
        """
        Executa benchmark completo.
        """

        if not self.queries_json:
            print("[ERRO] Nenhuma query carregada.")
            return

        print("\n================================================")
        print("INICIANDO COLETA DE BASELINE")
        print("================================================")

        print(f"Sistema : {self.sistema_id}")
        print(f"Dataset : {self.dataset}")
        print(f"Queries : {len(self.queries_json)}")
        print(f"Runs    : {repeticoes}")

        # -----------------------------------------------------
        # Warmup
        # -----------------------------------------------------

        self.executar_warmup(cursor)

        # -----------------------------------------------------
        # Coleta oficial
        # -----------------------------------------------------

        for r in range(1, repeticoes + 1):

            print(f"\n[RUN {r}/{repeticoes}]")

            for item in self.queries_json:

                query_id = item.get("id")
                titulo = item.get("titulo", "sem_titulo")
                categoria = item.get("categoria", "desconhecida")
                sql = item.get("sql")

                if not sql:
                    continue

                # Primeira repetição ~ aproximação cache frio
                cache = "cache quente"

                try:

                    inicio = time.perf_counter()

                    cursor.execute(sql)

                    resultados = (
                        cursor.fetchall()
                        if cursor.description
                        else []
                    )

                    fim = time.perf_counter()

                    tempo_ms = (fim - inicio) * 1000

                    num_tuplas = len(resultados)

                    self.registrar(
                        run=r,
                        query_id=query_id,
                        titulo=titulo,
                        categoria=categoria,
                        tempo_ms=tempo_ms,
                        num_tuplas=num_tuplas,
                        obs=cache
                    )

                    print(
                        f"  Q{query_id:<2} | "
                        f"{tempo_ms:>9.3f} ms | "
                        f"{num_tuplas:>6} tuplas"
                    )

                except Exception as e:

                    erro = str(e).replace("\n", " ")

                    print(
                        f"  Q{query_id:<2} | ERRO"
                    )

                    self.registrar(
                        run=r,
                        query_id=query_id,
                        titulo=titulo,
                        categoria=categoria,
                        tempo_ms=tempo_ms,
                        num_tuplas=num_tuplas,
                        obs=erro[:150]
                    )

        print("\n================================================")
        print("[OK] COLETA FINALIZADA")
        print("================================================")

        print(f"CSV:")
        print(self.caminho_saida)

        print(f"\nMetadados:")
        print(self.caminho_metadados)


    def executar_2k(self,
                    cursor,
                    config_experimento
                    ):
        matriz_base = ff2n(3)
        df_base = pd.DataFrame(matriz_base, columns=['A', 'B', 'C'])
        df_base['AB'] = df_base['A'] * df_base['B']
        df_base['AC'] = df_base['A'] * df_base['C']
        df_base['BC'] = df_base['B'] * df_base['C']
        df_base['ABC'] = df_base['A'] * df_base['B'] * df_base['C']
        print(df_base)

        kfatorial = KFactorial(cursor,self.queries_json,df_base,config_experimento)
        for indice, linha in kfatorial.tabela_sinais.iterrows():
            # Pegamos os níveis matemáticos (-1 ou 1) da linha atual:
            nivel_A = int(linha['A'])
            nivel_B = int(linha['B'])
            nivel_C = int(linha['C'])
    
    
            kfatorial.configura_quantidade(nivel_C)
            kfatorial.configura_ordem(nivel_A)
            kfatorial.configura_warmup(nivel_B)
            
            print(f"Configuração atual {linha.name}")
            print(f"Configuração atual A: {nivel_A}")
            print(f"COnfiguração atual B: {nivel_B}")
            print(f"Configuração atual C:{nivel_C}")
            
            self.queries_json = kfatorial.queries_selecionadas
            self.warmup = kfatorial.warmup
            self.executar_warmup(cursor)
            
            tempos_execucao = []
            total_tuplas = 0
            
            for item in kfatorial.queries_ordenadas:
                
                query_id = item.get("id")
                titulo = item.get("titulo", "sem_titulo")
                categoria = item.get("categoria", "desconhecida")
                sql = item.get("sql")

                if not sql:
                    continue

                # Primeira repetição ~ aproximação cache frio
                cache = "cache quente"

                try:

                    inicio = time.perf_counter()

                    cursor.execute(sql)

                    resultados = (
                        cursor.fetchall()
                        if cursor.description
                        else []
                    )

                    fim = time.perf_counter()

                    tempo_ms = (fim - inicio) * 1000

                    num_tuplas = len(resultados)

                    tempos_execucao.append(tempo_ms)
                    total_tuplas += num_tuplas

                    self.registrar(
                        run=0,
                        query_id=query_id,
                        titulo=titulo,
                        categoria=categoria,
                        tempo_ms=tempo_ms,
                        num_tuplas=num_tuplas,
                        obs=cache
                    )

                    print(
                        f"  Q{query_id:<2} | "
                        f"{tempo_ms:>9.3f} ms | "
                        f"{num_tuplas:>6} tuplas"
                    )

                except Exception as e:

                    erro = str(e).replace("\n", " ")

                    print(
                        f"  Q{query_id:<2} | ERRO"
                    )

                    self.registrar(
                        run=0,
                        query_id=query_id,
                        titulo=titulo,
                        categoria=categoria,
                        tempo_ms=tempo_ms,
                        num_tuplas=num_tuplas,
                        obs=erro[:150]
                    )

            if tempos_execucao:
                tempo_medio = sum(tempos_execucao) / len(tempos_execucao)
                df_base.loc[indice, 'tempo_media'] = tempo_medio
                df_base.loc[indice, 'num_tuplas'] = total_tuplas
                df_base.loc[indice, 'tuplas_milissegundo'] = total_tuplas / tempo_medio if tempo_medio > 0 else 0


        return df_base





    def executar_2kr(self,
                     cursor,
                     config_experimento,
                     repeticoes = 3,
                     ):
        """
        Executa Modelo de experimento 2kr fatorial
        """

        if not self.queries_json:
            print("[ERRO] Nenhuma query carregada.")
            return

        print("\n================================================")
        print("EXECUTANDO 2KR FATORIAL")
        print("================================================")

        print(f"Sistema : {self.sistema_id}")
        print(f"Dataset : {self.dataset}")
        print(f"Queries : {len(self.queries_json)}")
        print(f"Runs    : {repeticoes}")
        
        tabelas_de_sinais = []

        for i in range(0,repeticoes):
            tabelas_de_sinais.append(self.executar_2k(cursor,config_experimento))
        for i in range(0,repeticoes):
            print(f"\n=== RESULTADOS DO EXPERIMENTO {i+1} ===")
            print(tabelas_de_sinais[i].to_string())

        print("\n================================================")
        print("CONSOLIDANDO DATAFRAME FINAL COM AS MÉDIAS")
        print("================================================")

        colunas_base = ['A', 'B', 'C', 'AB', 'AC', 'BC', 'ABC']
        df_consolidado = tabelas_de_sinais[0][colunas_base].copy()

        ultimas_3_colunas = list(tabelas_de_sinais[0].columns[-3:])

        for metrica in ultimas_3_colunas:
            df_empilhado = pd.concat([df[metrica] for df in tabelas_de_sinais], axis=1)
    
            if metrica == 'tuplas_milissegundo':
                df_consolidado[metrica] = df_empilhado.apply(hmean, axis=1)
            else:
                df_consolidado[metrica] = df_empilhado.mean(axis=1)        

        calcular_variacao_explicada(df_consolidado, repeticoes=repeticoes)
        print(df_consolidado.to_string())
        





def calcular_variacao_explicada(df_consolidado, repeticoes=3):
    """
    Calcula os efeitos (q) e a porção de variação explicada para um modelo 2^3 r
    Baseado na métrica 'tuplas_milissegundo'
    """
    print("\n================================================")
    print("ANÁLISE DE VARIAÇÃO EXPLICADA (FÓRMULA DO PROFESSOR)")
    print("================================================")
    
    # 1. Número de experimentos na matriz base (2^3 = 8)
    N = 8 
    r = repeticoes
    
    # Lista dos fatores e interações presentes na tabela
    fatores = ['A', 'B', 'C', 'AB', 'AC', 'BC', 'ABC']
    
    # 2. Computar os efeitos (q) para cada fator/interação
    # Fórmula: q_i = (Soma de (Coluna_Sinal_i * Resposta_Media)) / N
    q = {}
    for f in fatores:
        # Produto escalar do sinal (-1 ou +1) pela média das vazões
        contraste = np.dot(df_consolidado[f], df_consolidado['tuplas_milissegundo'])
        q[f] = contraste / N

    # 3. Calcular a parcela de cada efeito na SST (Soma dos Quadrados Total dos Efeitos)
    # Fórmula da variação de cada efeito: V_i = 2^k * r * (q_i^2)
    parcelas_sst = {}
    sst_total_efeitos = 0
    
    for f in fatores:
        parcela = N * r * (q[f] ** 2)
        parcelas_sst[f] = parcela
        sst_total_efeitos += parcela
        
    # 4. Exibir os resultados formatados exatamente igual ao exemplo do professor
    print(f"SST (dos efeitos) = 2^{int(np.log2(N))} * r * (q_A² + q_B² + q_C² + q_AB² + q_AC² + q_BC² + q_ABC²)")
    
    # Monta a string da soma dos quadrados dos efeitos para conferência (usando .2f para não perder os decimais da vazão)
    termos_quadrados = " + ".join([f"({q[f]:.2f})²" for f in fatores])
    print(f"                  = {N} * {r} * ({termos_quadrados})")
    
    termos_valores = " + ".join([f"{parcelas_sst[f]:.2f}" for f in fatores])
    print(f"                  = {termos_valores} = {sst_total_efeitos:.2f}")
    
    print("\nPorção de variação explicada pelos efeitos:")
    print("------------------------------------------------")
    for f in fatores:
        porcentagem = (parcelas_sst[f] / sst_total_efeitos) * 100 if sst_total_efeitos > 0 else 0
        print(f"{f:<4}: {parcelas_sst[f]:.2f}/{sst_total_efeitos:.2f} ({porcentagem:.1f}%)")
    print("------------------------------------------------\n")
    
    # Cria um dicionário com os resultados caso queira usar depois
    resultados = {
        'efeitos_q': q,
        'parcelas_sst': parcelas_sst,
        'sst_total': sst_total_efeitos
    }
    return resultados


def main():
    config_experimento = {
        'A': {
            -1: 'diferentes',  # Queries com campos de busca diferentes juntas
            1: 'iguais'       # Queries com campos de busca iguais juntas
        },
        'B': {
            -1: 1,            # Número de consultas de warmup = 1
            1: 5              # Número de consultas de warmup = 5
    },
        'C': {
            -1: 20,           # Quantidade de queries = 20
            1: 100            # Quantidade de queries = 100
        }
    }

    args= parse_args()

    conexao= conecta(args.db_host, args.db_port, args.db_name, args.db_user, args.db_pass)
    if conexao is None:
        sys.exit(1)

    cursor=conexao.cursor()
    if cursor is None:
        desconecta(conexao)
        sys.exit(1)

    coletor = ColetorBenchmarkingBD(
            sistema_id="sistema_giovana",
            arquivo_queries="queries_100_gio.json",
            nome_arquivo="baseline_postgres.csv",
            dataset="amazon_2006",
        )

    coletor.salvar_metadados(
            db_versao="PostgreSQL 16",
            observacoes=(
                "Benchmark executado localmente "
                "com workload fixo."
            )
        )


    #coletor.executar_experimento(
    #        cursor,
    #        repeticoes=args.repeticoes
    #    )

    coletor.executar_2kr(
            cursor,
            config_experimento=config_experimento,
            repeticoes=args.repeticoes
    )

    desconecta_cursor(cursor)
    desconecta(conexao)

main()
sys.exit(0)
