# Ca-Mau-Museum-Pgsync

Real-time PostgreSQL to Elasticsearch synchronization for Cà Mau Museum using PGSync.

## 🚀 Features

- **PostgreSQL** 16.9 with logical replication enabled
- **Elasticsearch** 8.11.1 with Vietnamese analyzer support
- **Redis** for PGSync job queue
- **PGSync** for real-time data synchronization

## 📋 Prerequisites

- Docker Desktop or Podman installed
- At least 4GB RAM allocated to Docker/Podman

## 🛠️ Setup

### 1. Environment Configuration

The `.env` file contains all necessary environment variables:

- PostgreSQL connection settings
- Elasticsearch credentials
- Redis configuration
- PGSync parameters

### 2. Schema Configuration

Edit `schema.json` to define which tables to sync:

```json
[
  {
    "database": "postgresdb",
    "index": "camau_museum",
    "nodes": {
      "table": "your_table_name",
      "schema": "public",
      "columns": ["id", "name", "description", "created_at", "updated_at"]
    }
  }
]
```

### 3. Start Services

```bash
# Build Elasticsearch with Vietnamese analyzer (first time only)
podman build -t es8-with-vn-analyzer:0.0.1 -f elasticsearch-base.dockerFile .

# Start all services
podman-compose up -d

# Check service status
podman-compose ps

# View logs
podman-compose logs -f pgsync
```

### 4. Initialize PGSync

```bash
# Bootstrap the database (creates replication slot and triggers)
podman exec -it camau_museum_pgsync pgsync bootstrap

# Start syncing
podman-compose restart pgsync
```

## 📊 Verify Setup

### PostgreSQL

```bash
podman exec -it camau_museum_postgres psql -U postgres -d postgresdb
```

### Elasticsearch

```bash
curl -u elastic:mySecurePassword123 http://localhost:9200/_cat/health
curl -u elastic:mySecurePassword123 http://localhost:9200/_cat/indices
```

### Redis

```bash
podman exec -it camau_museum_redis redis-cli ping
```

## 🔄 PGSync Commands

```bash
# Bootstrap (run once)
podman exec -it camau_museum_pgsync pgsync bootstrap

# Full sync
podman exec -it camau_museum_pgsync pgsync --daemon

# Check sync status
podman-compose logs pgsync
```

## 📁 File Structure

```
.
├── docker-compose.yml          # Services orchestration
├── .env                        # Environment variables
├── schema.json                 # PGSync schema definition
├── postgresql.conf             # PostgreSQL config
├── elasticsearch-base.dockerFile # Custom ES with Vietnamese analyzer
└── README.md                   # This file
```

## 🔧 Troubleshooting

### PostgreSQL connection issues

- Ensure `listen_addresses = '*'` is in `postgresql.conf`
- Check if PostgreSQL is healthy: `podman-compose ps`

### Elasticsearch connection issues

- Verify credentials in `.env` match docker-compose.yml
- Check ES health: `curl -u elastic:mySecurePassword123 http://localhost:9200`

### PGSync not syncing

- Check if replication slot exists: `SELECT * FROM pg_replication_slots;`
- Verify schema.json matches your database tables
- Check PGSync logs: `podman-compose logs pgsync`

## 📚 Documentation

- [PGSync Documentation](https://pgsync.com/)
- [PGSync Environment Variables](https://pgsync.com/env-vars/)
- [PGSync Schema Definition](https://pgsync.com/schema/)
- [Vietnamese Analyzer](https://github.com/duydo/elasticsearch-analysis-vietnamese)

## 🔐 Security Notes

**⚠️ Important:** The passwords in this setup are for development only. For production:

1. Use strong, unique passwords
2. Store credentials in a secure secrets manager
3. Enable SSL/TLS for all connections
4. Restrict network access with firewalls
