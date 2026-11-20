#!/usr/bin/env bash
# scripts/init_postgres.sh
# Starts Postgres 16 Docker container and initializes airlock_core, airlock_in, and airlock_eu
set -e

CONTAINER_NAME="airlock-postgres"
PORT=5432
PASSWORD="postgres"

if [ "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo "Docker container $CONTAINER_NAME is already running."
elif [ "$(docker ps -aq -f status=exited -f name=$CONTAINER_NAME)" ]; then
    echo "Starting existing container $CONTAINER_NAME..."
    docker start $CONTAINER_NAME
else
    echo "Running new container $CONTAINER_NAME on port $PORT..."
    docker run -d --name $CONTAINER_NAME \
        -p $PORT:5432 \
        -e POSTGRES_PASSWORD=$PASSWORD \
        postgres:16-alpine
fi

echo "Waiting for PostgreSQL to be ready..."
until docker exec $CONTAINER_NAME pg_isready -U postgres > /dev/null 2>&1; do
    sleep 1
done

echo "Executing scripts/init_postgres.sql..."
docker exec -i $CONTAINER_NAME psql -U postgres < "$(dirname "$0")/init_postgres.sql" || true

echo "PostgreSQL setup complete with airlock_core, airlock_in, and airlock_eu."
