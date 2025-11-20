#!/usr/bin/env python3
"""
Patch PGSync to support DELETE operations in plugins
"""

import re
import sys
from pathlib import Path


def patch_sync_py(file_path):
    """Add plugin support to _delete_op method and add debug logging"""
    print(f"Patching {file_path}...")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Patch 1: Add debug logging at the start of _delete_op
    old_code_1 = """    def _delete_op(
        self, node: Node, filters: dict, payloads: t.List[dict]
    ) -> dict:
        # when deleting a root node, just delete the doc in
        # Elasticsearch/OpenSearch
        if node.is_root:"""
    
    new_code_1 = """    def _delete_op(
        self, node: Node, filters: dict, payloads: t.List[dict]
    ) -> dict:
        # ByteX Technology: Debug logging for DELETE operations
        print(f"[ByteX DELETE] _delete_op called: table={node.table}, is_root={node.is_root}, payloads={len(payloads)}")
        
        # when deleting a root node, just delete the doc in
        # Elasticsearch/OpenSearch
        if node.is_root:"""
    
    if old_code_1 in content:
        content = content.replace(old_code_1, new_code_1)
        print("✓ Added debug logging to _delete_op")
    else:
        print("✗ Could not add debug logging - checking if already patched")
    
    # Patch 2: Pass DELETE operations through plugins
    old_code_2 = """            if docs:
                raise_on_exception: t.Optional[bool] = (
                    False if settings.USE_ASYNC else None
                )
                raise_on_error: t.Optional[bool] = (
                    False if settings.USE_ASYNC else None
                )
                self.search_client.bulk(
                    self.index,
                    docs,
                    raise_on_exception=raise_on_exception,
                    raise_on_error=raise_on_error,
                )"""
    
    new_code_2 = """            # ByteX Technology: Log before plugin processing
            print(f"[ByteX DELETE] Processing {len(docs)} docs for deletion, has_plugins={self._plugins is not None}")
            
            if docs:
                # Pass DELETE operations through plugins (ByteX Technology modification)
                if self._plugins:
                    processed_docs: list = []
                    for doc, payload in zip(docs, payloads):
                        print(f"[ByteX DELETE] Processing doc {doc['_id']} through plugin")
                        # Add source data for plugin access
                        plugin_doc = {
                            "_id": doc["_id"],
                            "_index": doc["_index"],
                            "_source": payload.data,
                        }
                        
                        try:
                            result = next(self._plugins.transform(
                                [plugin_doc],
                                operation="delete"
                            ))
                            
                            print(f"[ByteX DELETE] Plugin returned result for {doc['_id']}: {result is not None}")
                            # Plugin can block delete by returning None
                            if result and result.get("_source") is not None:
                                processed_docs.append(doc)
                        except StopIteration:
                            # Plugin returned None, skip this document
                            print(f"[ByteX DELETE] Plugin blocked deletion of {doc['_id']}")
                            pass
                    
                    docs = processed_docs
                    print(f"[ByteX DELETE] After plugin processing: {len(docs)} docs remain")
                
                if docs:
                    print(f"[ByteX DELETE] Executing bulk delete for {len(docs)} docs")
                    raise_on_exception: t.Optional[bool] = (
                        False if settings.USE_ASYNC else None
                    )
                    raise_on_error: t.Optional[bool] = (
                        False if settings.USE_ASYNC else None
                    )
                    self.search_client.bulk(
                        self.index,
                        docs,
                        raise_on_exception=raise_on_exception,
                        raise_on_error=raise_on_error,
                    )"""
    
    if old_code_2 in content:
        content = content.replace(old_code_2, new_code_2)
        print("✓ Patched _delete_op method with plugin support and logging")
    else:
        print("✗ Could not find exact match in sync.py - checking if already patched")
        # Check if already patched
        if "ByteX Technology modification" in content:
            print("✓ Appears to be already patched")
            return True
        return False
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    return True


def patch_trigger_py(file_path):
    """Fix trigger to include indices for DELETE operations"""
    print(f"Patching {file_path}...")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # The DELETE block currently doesn't fetch _indices
    old_code = """    IF TG_OP = 'DELETE' THEN

        SELECT primary_keys INTO _primary_keys
        FROM {MATERIALIZED_VIEW}
        WHERE table_name = TG_TABLE_NAME;

        old_row = ROW_TO_JSON(OLD);
        old_row := (
            SELECT JSONB_OBJECT_AGG(key, value)
            FROM JSON_EACH(old_row)
            WHERE key = ANY(_primary_keys)
        );
        xmin := OLD.xmin;"""
    
    # Fixed version that includes _indices
    new_code = """    IF TG_OP = 'DELETE' THEN

        SELECT primary_keys, indices INTO _primary_keys, _indices
        FROM {MATERIALIZED_VIEW}
        WHERE table_name = TG_TABLE_NAME;

        old_row = ROW_TO_JSON(OLD);
        old_row := (
            SELECT JSONB_OBJECT_AGG(key, value)
            FROM JSON_EACH(old_row)
            WHERE key = ANY(_primary_keys)
        );
        xmin := OLD.xmin;"""
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        print("✓ Patched DELETE trigger to include indices")
    else:
        print("✗ Could not find exact match in trigger.py - checking if already patched")
        if "SELECT primary_keys, indices INTO _primary_keys, _indices" in content:
            print("✓ Appears to be already patched")
            return True
        return False
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    return True


def patch_plugin_py(file_path):
    """Add operation parameter to transform method"""
    print(f"Patching {file_path}...")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find the transform method
    old_code = """    def transform(self, docs: t.Iterable[dict]) -> t.Generator:
        \"\"\"Applies all plugins to each doc.\"\"\"
        for doc in docs:
            for plugin in self.plugins:
                doc["_source"] = plugin.transform(
                    doc["_source"],
                    _id=doc["_id"],
                    _index=doc["_index"],
                )
                if not doc["_source"]:
                    yield
            yield doc"""
    
    new_code = """    def transform(self, docs: t.Iterable[dict], operation: str = None) -> t.Generator:
        \"\"\"Applies all plugins to each doc.\"\"\"
        for doc in docs:
            for plugin in self.plugins:
                # Build kwargs with optional operation parameter (ByteX Technology modification)
                kwargs = {
                    "_id": doc["_id"],
                    "_index": doc["_index"],
                }
                if operation:
                    kwargs["operation"] = operation
                
                doc["_source"] = plugin.transform(
                    doc["_source"],
                    **kwargs
                )
                if not doc["_source"]:
                    yield
            yield doc"""
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        print("✓ Patched transform method in plugin.py")
    else:
        print("✗ Could not find exact match in plugin.py - manual patching may be needed")
        return False
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    return True


def main():
    pgsync_dir = Path(__file__).parent
    
    sync_py = pgsync_dir / "pgsync" / "sync.py"
    plugin_py = pgsync_dir / "pgsync" / "plugin.py"
    trigger_py = pgsync_dir / "pgsync" / "trigger.py"
    
    if not sync_py.exists():
        print(f"Error: {sync_py} not found")
        sys.exit(1)
    
    if not plugin_py.exists():
        print(f"Error: {plugin_py} not found")
        sys.exit(1)
    
    if not trigger_py.exists():
        print(f"Error: {trigger_py} not found")
        sys.exit(1)
    
    print("=" * 60)
    print("PGSync Plugin DELETE Support Patch")
    print("ByteX Technology - Cà Mau Museum Project")
    print("=" * 60)
    print()
    
    success = True
    success = patch_sync_py(sync_py) and success
    success = patch_trigger_py(trigger_py) and success
    success = patch_plugin_py(plugin_py) and success
    
    print()
    if success:
        print("=" * 60)
        print("✓ Patching completed successfully!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Build Docker image: docker build -t pgsync-bytex:latest .")
        print("2. Update docker-compose.yml to use: pgsync-bytex:latest")
        print("3. Recreate triggers: bootstrap the schema")
        print("4. Test with your ArtifactFilter plugin")
    else:
        print("=" * 60)
        print("✗ Patching failed - manual intervention required")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
