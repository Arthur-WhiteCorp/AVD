# 1) Construir e subir os serviços

```
docker compose up -d --build
```

# 2) Conferir saúde do PostgreSQL

```
docker compose ps
```

# 3) Criar esquema e carregar dados

```
docker compose run --rm app python src/tp1_3.2.py --db-host db --db-port 5432 --db-name ecommerce --db-user postgres --db-pass postgres --input /data/snap_amazon.txt
```

# 4) Executar o dashboard

```
docker compose run --rm app python src/tp1_3.3.py --db-host db --db-port 5432 --db-name ecommerce --db-user postgres --db-pass postgres --output /app/out --product-asin [ asin do produto ]
```
Caso não especificado o comando --output, o resultado da consulta será printado na tela.