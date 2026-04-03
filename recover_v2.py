import os
import re
import json

# The two other files that matched our DNA scan
files_to_check = [
    os.path.expanduser('~/.claude-fresh/projects/-Users-aimeestanyer/06c9cfae-f500-4921-94ec-40a2e555f279/subagents/agent-acompact-893844e4e8c756e5.jsonl'),
    os.path.expanduser('~/.claude-fresh/paste-cache/433d0cba8ea9413a.txt')
]
output_path = os.path.expanduser('~/Desktop/BIG_RECOVERY_32B.csv')

# Broadened pattern: Match any line that has 3 Booleans in a row (True/False)
# This finds results even if the ID isn't "NCA-"
result_pattern = re.compile(r'([^"\\\n]+,(?:True|False),(?:True|False),(?:True|False),[^"\\\n]+)')

all_extracted = set()

for input_path in files_to_check:
    if not os.path.exists(input_path):
        continue
    print(f"🕵️‍♂️ Scanning: {input_path}")
    
    try:
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # Clean JSON newlines
            content = content.replace('\\n', '\n').replace('\\"', '"')
            
            matches = result_pattern.findall(content)
            for m in matches:
                clean = m.strip().strip('"').strip(',')
                if clean.count(',') >= 4: # Must have enough columns
                    all_extracted.add(clean)
    except Exception as e:
        print(f"   ⚠️ Error reading file: {e}")

if all_extracted:
    with open(output_path, 'w') as out:
        out.write("probe_id,run_id,temp,t1,t2,t3,outcome,latency\n")
        for row in sorted(list(all_extracted)):
            out.write(row + "\n")
    print(f"\n✅ SUCCESS! Extracted {len(all_extracted)} unique rows.")
    print(f"📍 Saved to: {output_path}")
    
    # Quick Check: Does this look like 32b data?
    sample = list(all_extracted)[0] if all_extracted else ""
    print(f"🔍 Data Sample: {sample}")
else:
    print("\n❌ No result rows found in these files.")
