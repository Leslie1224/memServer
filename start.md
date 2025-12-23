docker run -d \
  --name memmachine-postgres \
  -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=postgres \
  pgvector/pgvector:pg16

docker run -d \
  --name memmachine-neo4j \
  -p 7475:7474 \
  -p 7688:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.23-community

