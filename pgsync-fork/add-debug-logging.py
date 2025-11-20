#!/usr/bin/env python3
"""
Add debug logging to PGSync querybuilder to diagnose child relationship issues
"""

import sys
from pathlib import Path


def patch_querybuilder():
    """Add extensive debug logging to querybuilder.py"""
    file_path = Path(__file__).parent / "pgsync" / "querybuilder.py"
    print(f"Patching {file_path}...")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Patch 1: Add logging at the start of _children
    old_code_1 = """    def _children(self, node: Node) -> None:
        for child in node.children:
            onclause: t.List = []"""
    
    new_code_1 = """    def _children(self, node: Node) -> None:
        print(f"[DEBUG _children] Processing node: {node.table}, children count: {len(node.children)}")
        for child in node.children:
            print(f"[DEBUG _children] Processing child: {child.table}, label: {child.label}, parent: {child.parent.table}")
            onclause: t.List = []"""
    
    if old_code_1 in content:
        content = content.replace(old_code_1, new_code_1)
        print("✓ Added logging to _children method start")
    else:
        print("✗ Could not add _children start logging")
        return False
    
    # Patch 2: Add logging after foreign key lookup
    old_code_2 = """                foreign_keys: dict = self.get_foreign_keys(node, child)
                left_foreign_keys: list = self._get_column_foreign_keys(
                    child._subquery.columns,
                    foreign_keys,
                )"""
    
    new_code_2 = """                foreign_keys: dict = self.get_foreign_keys(node, child)
                print(f"[DEBUG _children] FK lookup: {node.table} -> {child.table}, result: {foreign_keys}")
                left_foreign_keys: list = self._get_column_foreign_keys(
                    child._subquery.columns,
                    foreign_keys,
                )
                print(f"[DEBUG _children] left_foreign_keys: {left_foreign_keys}")"""
    
    if old_code_2 in content:
        content = content.replace(old_code_2, new_code_2)
        print("✓ Added FK lookup logging")
    else:
        print("✗ Could not add FK lookup logging")
        return False
    
    # Patch 3: Add logging before join
    old_code_3 = """            op = sa.and_
            if child.table == child.parent.table:
                op = sa.or_
            self.from_obj = self.from_obj.join(
                child._subquery,
                onclause=op(*onclause),
                isouter=self.isouter,
            )"""
    
    new_code_3 = """            op = sa.and_
            if child.table == child.parent.table:
                op = sa.or_
            print(f"[DEBUG _children] Creating join for {child.table}, onclause count: {len(onclause)}")
            if len(onclause) == 0:
                print(f"[DEBUG _children] WARNING: Empty onclause for {child.table}! This will create a CROSS JOIN!")
            self.from_obj = self.from_obj.join(
                child._subquery,
                onclause=op(*onclause),
                isouter=self.isouter,
            )
            print(f"[DEBUG _children] Join created for {child.table}")"""
    
    if old_code_3 in content:
        content = content.replace(old_code_3, new_code_3)
        print("✓ Added join logging")
    else:
        print("✗ Could not add join logging")
        return False
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("✓ Debug logging added successfully!")
    return True


if __name__ == "__main__":
    if patch_querybuilder():
        print("\nDebug logging has been added to querybuilder.py")
        print("Rebuild the Docker image to apply changes")
        sys.exit(0)
    else:
        print("\nFailed to add debug logging")
        sys.exit(1)
