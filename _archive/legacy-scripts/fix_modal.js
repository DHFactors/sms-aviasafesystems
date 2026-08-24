import re

with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# Fix 1: Replace hero button onclick
# Current: onclick="toggleModal()"
# Target: onclick="document.getElementById('demo-modal').classList.remove('hidden')"
old_onclick = 'onclick="toggleModal()"'
new_onclick = "onclick=\"document.getElementById('demo-modal').classList.remove('hidden')\""

if old_onclick in content:
    content = content.replace(old_onclick, new_onclick)
    print('Fix 1: Replaced hero button onclick')
else:
    print('Fix 1: old onclick not found')

# Fix 2: Update modal container z-index
# Current: class="fixed inset-0 z-50 hidden flex items-center justify-center bg-black bg-opacity-60 backdrop-blur-sm"
# Target: class="fixed inset-0 z-[9999] hidden flex items-center justify-center bg-black bg-opacity-60 backdrop-blur-sm"
old_modal_class = 'class="fixed inset-0 z-50 hidden flex items-center justify-center bg-black bg-opacity-60 backdrop-blur-sm"'
new_modal_class = 'class="fixed inset-0 z-[9999] hidden flex items-center justify-center bg-black bg-opacity-60 backdrop-blur-sm"'

if old_modal_class in content:
    content = content.replace(old_modal_class, new_modal_class)
    print('Fix 2: Updated modal z-index to z-[9999]')
else:
    print('Fix 2: old modal class not found')

# Fix 3: Update close button onclick
# Current: onclick="toggleModal()"
# Target: onclick="document.getElementById('demo-modal').classList.add('hidden')"
old_close_btn = 'onclick="toggleModal()"'
new_close_btn = "onclick=\"document.getElementById('demo-modal').classList.add('hidden')\""

# Replace the specific close button onclick in the modal
if 'onclick="toggleModal()"' in content:
    content = content.replace(old_close_btn, new_close_btn)
    print('Fix 3: Replaced close button onclick')
else:
    print('Fix 3: old close button onclick not found')

# Fix 4: Remove any toggleModal() function definition script at the bottom
script_tag_start = content.rfind('<script')
if script_tag_start >= 0:
    script_tag_end = content.rfind('</script>') + len('</script>')
    script_content = content[script_tag_start:script_tag_end]
    if 'function toggleModal' in script_content:
        # Remove the entire script tag
        content = content[:script_tag_start] + content[script_tag_end:]
        print('Fix 4: Removed toggleModal() function script')
    else:
        print('Fix 4: No toggleModal() function found in script tags')

# Write the updated content
with open('public/index.html', 'w', errors='replace') as f:
    f.write(content)
print('\\nAll fixes applied and file updated')