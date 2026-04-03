import os
import re

input_path = os.path.expanduser('~/.claude-fresh/projects/-Users-aimeestanyer/06c9cfae-f500-4921-94ec-40a2e555f279.jsonl')
output_path = os.path.expanduser('~/Desktop/RECOVERED_32B_DATA.csv')

print(f"Reading Jackpot File: {input_path}")

# Regex to find NCA-001 through NCA-499 even if escaped as \"NCA-001\"
pattern = re.compile(r'NCA-\d{3},[^\"]+')

results = set()

try:
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        # Clean the raw blob of JSON newline escapes so regex works across lines
        content = content.replace('\\n', '\n')
        matches = pattern.findall(content)
        
        for m in matches:
            # Final cleanup of any lingering JSON junk
            clean = m.split('\\')[0].strip()
            if clean.count(',') >= 3:
                results.add(clean)

    if results:
        with open(output_path, 'w') as out:
            out.write("probe_id,run_id,temp,t1,t2,t3,outcome,latency\n")
            for row in sorted(list(results)):
                out.write(row + "\n")
        print(f"✅ SUCCESS: Extracted {len(results)} rows to Desktop/RECOVERED_32B_DATA.csv")
    else:
        print("❌ Found the file, but no data rows inside. They might be in the other .jsonl file.")

except Exception as e:
    print(f"❌ Error: {e}")
