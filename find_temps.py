import os

search_paths = [
    os.path.expanduser('~/Projects/control-plane-3'),
    os.path.expanduser('~/Desktop/RECOVERY_ZONE'),
    os.path.expanduser('~/.Trash') # Checking the trash just in case
]

targets = ['deepseek', 'qwen3', '32b', 'distill']

print("🔍 Hunting for specific 'temp_' result files...")

for base in search_paths:
    if not os.path.exists(base): continue
    for root, _, files in os.walk(base):
        for f in files:
            f_lower = f.lower()
            # Look for temp files or files containing our model keywords
            if ('temp_' in f_lower or 'fw_' in f_lower) and any(t in f_lower for t in targets):
                f_path = os.path.join(root, f)
                try:
                    size = os.path.getsize(f_path) / 1024
                    with open(f_path, 'r', errors='ignore') as file:
                        lines = sum(1 for _ in file)
                    
                    print(f"\n🎯 FOUND TARGET: {f_path}")
                    print(f"   Lines: {lines} | Size: {size:.1f} KB")
                    
                    # Peek to see if it has the NCA signature
                    with open(f_path, 'r', errors='ignore') as file:
                        header = file.readline().strip()
                        print(f"   Header: {header[:100]}")
                except:
                    continue
