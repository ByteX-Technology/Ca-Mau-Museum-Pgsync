#!/bin/bash

# PGSync Helper Script

case "$1" in
  bootstrap)
    echo "Bootstrapping PGSync (creating replication slot and triggers)..."
    podman exec -it camau_museum_pgsync pgsync bootstrap
    ;;
  
  sync)
    echo "Starting manual sync..."
    podman exec -it camau_museum_pgsync pgsync
    ;;
  
  status)
    echo "Checking PGSync status..."
    podman-compose logs --tail=50 pgsync
    ;;
  
  restart)
    echo "Restarting PGSync..."
    podman-compose restart pgsync
    ;;
  
  check-slot)
    echo "Checking PostgreSQL replication slot..."
    podman exec -it camau_museum_postgres psql -U postgres -d postgresdb -c "SELECT * FROM pg_replication_slots;"
    ;;
  
  check-indices)
    echo "Checking Elasticsearch indices..."
    curl -u elastic:mySecurePassword123 http://localhost:9200/_cat/indices?v
    ;;
  
  test-es)
    echo "Testing Elasticsearch connection..."
    curl -u elastic:mySecurePassword123 http://localhost:9200/_cluster/health?pretty
    ;;
  
  test-pg)
    echo "Testing PostgreSQL connection..."
    podman exec -it camau_museum_postgres psql -U postgres -d postgresdb -c "SELECT version();"
    ;;
  
  logs)
    echo "Tailing all logs..."
    podman-compose logs -f
    ;;
  
  *)
    echo "PGSync Helper - Cà Mau Museum"
    echo ""
    echo "Usage: $0 {command}"
    echo ""
    echo "Commands:"
    echo "  bootstrap      - Initialize PGSync (run once)"
    echo "  sync           - Trigger manual sync"
    echo "  status         - Show PGSync logs"
    echo "  restart        - Restart PGSync service"
    echo "  check-slot     - Check PostgreSQL replication slot"
    echo "  check-indices  - List Elasticsearch indices"
    echo "  test-es        - Test Elasticsearch connection"
    echo "  test-pg        - Test PostgreSQL connection"
    echo "  logs           - Tail all service logs"
    echo ""
    exit 1
    ;;
esac
