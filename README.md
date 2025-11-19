# Ca Mau Museum - PGSync Search Integration

Real-time synchronization of museum artifacts and relics from PostgreSQL to Elasticsearch for unified search functionality.

## Overview

This project syncs museum data from PostgreSQL to Elasticsearch, providing:

- **Unified Search**: Single `cmm-search` alias for searching both artifacts (hiện vật) and relics (di tích)
- **Real-time Sync**: Automatic synchronization using PostgreSQL logical replication
- **Vietnamese Text**: Full Vietnamese text analysis with custom analyzers
- **Field Transformation**: Smart data transformation via custom plugins

## Architecture

```
PostgreSQL (Source)
    ├── HoSo → ChiTietHienVat (Artifacts)
    └── HoSo → ChiTietDiTich (Relics)
                    ↓
                PGSync
                    ↓
              Elasticsearch
    ├── cmm-search-artifact index
    ├── cmm-search-relic index
    └── cmm-search alias (unified search)
```

## Indexes

### cmm-search-artifact

Syncs museum artifacts with:

- **Source**: `ChiTietHienVat` table
- **Images**: First image from `HinhAnhHienVat`
- **Classification**: `ThuocNhom = "Hiện vật"`

### cmm-search-relic

Syncs historical relics with:

- **Source**: `ChiTietDiTich` table
- **Tags**: Latest `Nhan` from `DsHangDiTich` (sorted by `ThoiGianTao` DESC)
- **Images**: First image from `DsAnhDiTich`
- **Classification**: `ThuocNhom = "Di tích"`

## Field Mappings

| Elasticsearch Field | Artifact Source             | Relic Source               |
| ------------------- | --------------------------- | -------------------------- |
| `TieuDe`            | `TenHienVat`                | `TenDiTich`                |
| `MoTa`              | `MieuTa`                    | `MoTaNgan`                 |
| `SoDangKy`          | `SoDangKy`                  | `MaDiTich`                 |
| `ThuocNhom`         | "Hiện vật"                  | "Di tích"                  |
| `Nhan`              | -                           | Latest from `DsHangDiTich` |
| `MaSoAnhDaiDien`    | First from `HinhAnhHienVat` | First from `DsAnhDiTich`   |
| `KhoaAnhDaiDien`    | First from `HinhAnhHienVat` | First from `DsAnhDiTich`   |

## Services

- **PostgreSQL**: Source database with logical replication enabled
- **Elasticsearch**: Search engine with Vietnamese analyzer
- **Redis**: PGSync queue for change tracking
- **Elasticsearch Init**: Automated template setup on startup
- **PGSync**: Real-time synchronization daemon

## Quick Start

See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed setup instructions.

```bash
# Start all services
podman-compose up -d

# Check status
podman ps

# View PGSync logs
podman logs -f camau_museum_pgsync
```

## Search Examples

### Search across all items (artifacts + relics)

```bash
curl -X GET "localhost:9200/cmm-search/_search?q=gốm"
```

### Search only artifacts

```bash
curl -X GET "localhost:9200/cmm-search-artifact/_search?q=gốm"
```

### Search only relics

```bash
curl -X GET "localhost:9200/cmm-search-relic/_search?q=đình"
```

### Advanced query with Vietnamese analyzer

```json
{
  "query": {
    "multi_match": {
      "query": "gốm sứ",
      "fields": ["TieuDe", "MoTa"],
      "type": "best_fields",
      "analyzer": "vi_analyzer"
    }
  }
}
```

## Custom Plugin

The `ArtifactFilterPlugin` handles:

- Document filtering by `TrangThai` (status)
- Field transformations and mappings
- Image extraction (first image from related tables)
- Tag extraction (`Nhan` from latest `DsHangDiTich`)
- DELETE, INSERT, UPDATE operations

Location: `plugins/artifactfilter.py`

## Configuration Files

- `schema.json`: PGSync table mappings and relationships
- `docker-compose.yml`: Service orchestration
- `setup-index-templates.py`: Elasticsearch template initialization
- `plugins/artifactfilter.py`: Custom data transformation logic
- `pgsync-entrypoint.sh`: PGSync startup script

## Monitoring

```bash
# Check Elasticsearch health
curl -u elastic:password http://localhost:9200/_cluster/health

# View indexes
curl -u elastic:password http://localhost:9200/_cat/indices?v

# Check aliases
curl -u elastic:password http://localhost:9200/_cat/aliases?v

# View template
curl -u elastic:password http://localhost:9200/_index_template/cmm-search-template
```

## Troubleshooting

### PGSync not syncing

1. Check database has tables: `podman exec camau_museum_postgres psql -U postgres -c "\dt"`
2. Verify replication slot: Check PGSync logs
3. Check Redis connection: `podman logs camau_museum_redis`

### Template not created

1. Check init container: `podman logs camau_museum_es_init`
2. Verify Elasticsearch health: `curl localhost:9200/_cluster/health`
3. Manually run: `python3 setup-index-templates.py`

### Search not working

1. Check indexes exist: `curl localhost:9200/_cat/indices`
2. Verify alias: `curl localhost:9200/_cat/aliases`
3. Check document count: `curl localhost:9200/cmm-search/_count`

## Development

### Adding new fields

1. Update `schema.json` with new columns
2. Update `setup-index-templates.py` with field mappings
3. Update `plugins/artifactfilter.py` if transformation needed
4. Restart services: `podman-compose restart pgsync`

### Testing plugin changes

```bash
# Reload schema
podman exec camau_museum_pgsync pgsync bootstrap --config /config/schema.json

# Watch logs
podman logs -f camau_museum_pgsync
```

## License

Copyright © 2025 ByteX Technology

## Support

For issues or questions, contact the development team.
