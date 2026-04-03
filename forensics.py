import os
import sqlite3

search_paths = [
    os.path.expanduser('~/Desktop/RECOVERY_ZONE'),
    os.path.expanduser('~/Projects/control-plane-3'),
    os.path.expanduser('~/.claude-fresh')
]

print("🔍 STARTING FULL FORENSIC SWEEP (Size + Content + SQLite)...")

# 1. SCAN FOR TEXT FILES (CSV/JSON/LOG)
for base in search_paths:
    if not os.path.exists(base): continue
    for root, _, files in os.walk(base):
        for f in files:
            if f.startswith('.') or f.endswith(('.pdf', '.png', '.zip', '.py')): continue
            f_path = os.path.join(root, f)
            try:
                size_kb = os.path.getsize(f_path) / 1024
                # Looking for files that 'weigh' like 200-500 probe sets
                if 100 < size_kb < 3000:
                    with open(f_path, 'r', encoding='utf-8', errors='ignore') as file:
                        peek = file.read(2000).lower()
                        if "nca-001" in peek or "probe_id" in peek:
                            file.seek(0)
                            lines = sum(1 for _ in file)
                            if lines > 150:
                                print(f"\n💎 TEXT DATA FOUND: {f_path}")
                                print(f"   Size: {size_kb:.1f} KB | Lines: {lines}")
                                hints = [h for h in ['qwen', 'distill', '32b', 'europe', 'amazon', 'bedrock', 'eu-'] if h in peek or h in f_path.lower()]
                                print(f"   🏷️  Hints: {hints}")
            except: continue

# 2. SCAN FOR HIDDEN SQLITE DATABASES
for base in search_paths:
    if not os.path.exists(base): continue
    for root, _, files in os.walk(base):
        for f in files:
            if f.endswith('.db'):
                db_path = os.path.join(root, f)
                try:
                    conn = sqlite3.connect(db_path)
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs';")
                    if cur.fetchone():
                        cur.execute("""
                            SELECT model, dataset, COUNT(*) 
                            FROM runs r JOIN results res ON r.id = res.run_id 
                            WHERE model LIKE '%32%' OR model LIKE '%qwen%' OR model LIKE '%distill%'
                            GROUP BY model, dataset;
                        """)
                        rows = cur.fetchall()
                        if rows:
                            print(f"\n🗄️  DATA FOUND IN SQLITE: {db_path}")
                            for r in rows:
                                print(f"   Model: {r[0]} | Dataset: {r[1]} | Count: {r[2]}")
                    conn.close()
                except: continue

print("\n✅ Sweep Complete.")
