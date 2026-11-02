docker rm -f leme-pg leme-redis >/dev/null 2>&1
docker run -d --name leme-pg --network sora-leme -e POSTGRES_PASSWORD=t -e POSTGRES_USER=t -e POSTGRES_DB=t pgvector/pgvector:pg16 >/dev/null
docker run -d --name leme-redis --network sora-leme redis:7 >/dev/null
sleep 6
