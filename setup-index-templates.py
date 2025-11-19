#!/usr/bin/env python3
"""
Setup Elasticsearch index templates for cmm-search indexes
"""
import os
import sys
import json
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from base64 import b64encode

# Elasticsearch credentials from environment or defaults
ES_HOST = os.getenv('ELASTICSEARCH_HOST', 'http://elasticsearch:9200')
ES_USER = os.getenv('ELASTIC_USER', 'elastic')
ES_PASS = os.getenv('ELASTIC_PASSWORD', 'mySecurePassword123')


def make_request(url, method='GET', data=None):
    """Make HTTP request to Elasticsearch"""
    credentials = f"{ES_USER}:{ES_PASS}".encode('utf-8')
    auth_header = b64encode(credentials).decode('ascii')

    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/json'
    }

    if data:
        data = json.dumps(data).encode('utf-8')

    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            return json.loads(error_body)
        except:
            return {'error': error_body, 'status': e.code}
    except URLError as e:
        return {'error': str(e), 'status': 'connection_error'}


def wait_for_elasticsearch(max_retries=30, delay=2):
    """Wait for Elasticsearch to be ready"""
    print("⏳ Waiting for Elasticsearch to be ready...")
    for i in range(max_retries):
        try:
            result = make_request(ES_HOST)
            if 'version' in result:
                print(
                    f"✅ Elasticsearch {result['version']['number']} is ready")
                return True
        except:
            pass

        if i < max_retries - 1:
            time.sleep(delay)
            print(f"   Retrying... ({i+1}/{max_retries})")

    print("❌ Elasticsearch is not available")
    return False


def create_template():
    """Create index template for cmm-search-* indexes (creates only if not exists)"""
    print("\n🔧 Setting up Elasticsearch index template...")

    # Check if template already exists
    check_url = f"{ES_HOST}/_index_template/cmm-search-template"
    existing = make_request(check_url)

    if 'index_templates' in existing and len(existing['index_templates']) > 0:
        print("✅ Template already exists, skipping creation")
        return True

    template = {
        "index_patterns": ["cmm-search-*"],
        "template": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "analysis": {
                    "analyzer": {
                        "vi_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "asciifolding"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "idGoc": {"type": "long"},
                    "TieuDe": {
                        "type": "text",
                        "analyzer": "vi_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "MoTa": {
                        "type": "text",
                        "analyzer": "vi_analyzer"
                    },
                    "ThoiGianTao": {"type": "date"},
                    "ThoiGianCapNhat": {"type": "date"},
                    "ThuocNhom": {"type": "keyword"},
                    "Nhan": {"type": "keyword"},
                    "MaSoAnhDaiDien": {"type": "keyword"},
                    "KhoaAnhDaiDien": {"type": "keyword"}
                }
            },
            "aliases": {
                "cmm-search": {}
            }
        },
        "priority": 500
    }

    print("📦 Creating template for cmm-search-*...")
    url = f"{ES_HOST}/_index_template/cmm-search-template"
    result = make_request(url, method='PUT', data=template)

    if result.get('acknowledged'):
        print("✅ Index template created successfully!")
        return True
    else:
        print(f"❌ Failed to create template: {result.get('error', result)}")
        return False


def verify_template():
    """Verify template was created"""
    print("\n📋 Verifying template...")
    url = f"{ES_HOST}/_index_template/cmm-search-template"
    result = make_request(url)

    if 'index_templates' in result and len(result['index_templates']) > 0:
        template = result['index_templates'][0]
        name = template['name']
        patterns = template['index_template']['index_patterns']
        print(f"  ✓ {name}: {', '.join(patterns)}")
        return True
    else:
        print("  ⚠ Template not found")
        return False


def verify_aliases():
    """Verify aliases (if indexes exist)"""
    print("\n🔍 Verifying aliases...")
    url = f"{ES_HOST}/_alias/cmm-search"
    result = make_request(url)

    if 'error' not in result and result:
        for index_name in result.keys():
            print(f"  ✓ {index_name} → cmm-search")
        return True
    else:
        print("  ⚠ No indexes created yet (will be created on bootstrap)")
        return True


def main():
    """Main setup function"""
    print("🚀 Elasticsearch Index Template Setup")
    print("=" * 50)

    # Wait for Elasticsearch
    if not wait_for_elasticsearch():
        sys.exit(1)

    # Create template
    if not create_template():
        sys.exit(1)

    # Verify
    verify_template()
    verify_aliases()

    print("\n✅ Setup complete!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
