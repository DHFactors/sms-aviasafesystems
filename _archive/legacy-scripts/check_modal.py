import re

with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# Check for toggleDemoModal function
if 'toggleDemoModal' in content:
    print('toggleDemoModal function EXISTS')
else:
    print('toggleDemoModal function NOT found')

# Check the close button onclick
for m in re.finditer(r'onclick', content):
    idx = m.start()
    context = content[max(0,idx-60):idx+30]
    print('onclick context:', context)

# Check modal div for z-index and classes
if 'id="demo-modal"' in content:
    idx = content.find('id="demo-modal"')
    start = max(0, idx-50)
    end = min(len(content), idx+150)
    print('Modal div context:')
    print(content[start:end])
"