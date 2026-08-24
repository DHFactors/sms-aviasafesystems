import re

with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# 1. Add toggleDemoModal function before </body>
body_end = content.rfind('</body>')
if body_end >= 0:
    new_function = '\n<script>\nfunction toggleDemoModal() {\n    const modal = document.getElementById(\'demo-modal\');\n    if (modal) {\n        modal.classList.add(\'hidden\');\n    }\n}\n</script>\n'
    
    content = content[:body_end] + new_function + content[body_end:]
    print('Added toggleDemoModal function')
else:
    print('</body> not found')

# 2. Update the close button onclick
old_onclick = "onclick=\"document.getElementById('demo-modal').classList.remove('hidden')\""
new_onclick = "onclick=\"toggleDemoModal()\""

if old_onclick in content:
    content = content.replace(old_onclick, new_onclick)
    print('Updated close button onclick')
else:
    print('Old onclick not found')

# 3. Add cursor-pointer to close button class
old_btn_class = 'class="absolute top-3 right-3 text-slate-600 hover:text-slate-900 rounded-full p-1"'
new_btn_class = 'class="absolute top-3 right-3 text-slate-600 hover:text-slate-900 rounded-full p-1 cursor-pointer"'

if old_btn_class in content:
    content = content.replace(old_btn_class, new_btn_class)
    print('Added cursor-pointer to close button')
else:
    print('Button class not found exact match')

# 4. Ensure modal has z-50 (if not already z-[9999])
# Check and add z-50 if needed
if 'z-50' not in content and 'z-[9999]' not in content:
    # Try to add z-50 somewhere appropriate
    print('Checking for z-index classes...')

# Write back
with open('public/index.html', 'w', errors='replace') as f:
    f.write(content)
print('\\nFile updated')