with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

results = []

# Check 1: toggleDemoModal function
results.append(('toggleDemoModal function', 'function toggleDemoModal' in content))

# Check 2: cursor-pointer
results.append(('cursor-pointer class', 'cursor-pointer' in content))

# Check 3: close button onclick has toggleDemoModal
import re
close_found = False
for m in re.finditer(r'onclick', content):
    context = content[max(0,m.start()-50):m.start()+50]
    if 'toggleDemoModal' in context:
        close_found = True
results.append(('close button onclick', close_found))

# Check 4: demo-modal ID
results.append(('demo-modal ID', 'id="demo-modal"' in content))

for name, result in results:
    status = 'PASS' if result else 'FAIL'
    print(f'[{status}] {name}')
"