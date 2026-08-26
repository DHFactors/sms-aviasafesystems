with open('public/index.html', 'r', errors='replace') as f:
    c = f.read()

# Find the a tag and replace with button
a_start = c.find('<a class=\"')
if a_start >= 0:
    a_end = content.find('</a>', a_start)
    if a_end >= 0:
        old_tag = content[a_start:a_end+4]
        new_tag = '<button type="button" class="w-full sm:w-auto px-8 py-4 text-base font-bold text-white bg-gradient-to-r from-brand-600 to-teal-600 hover:from-brand-700 hover:to-teal-600 rounded-xl shadow-lg shadow-brand-500/30 transition-all hover:scale-[1.02] flex items-center justify-center gap-3 cursor-pointer onclick="toggleDemoModal()"><i class="fa-solid fa-rocket text-lg"></i> Request Demo</button>'
        
        if old_tag in content:
            content = content.replace(old_tag, new_tag)
            with open('public/index.html', 'w', errors='replace') as f:
                f.write(content)
            print('Successfully converted a tag to button tag')
        else:
            print('Old tag not found')
            print('Tag start index:', a_start)
            print('Tag end:', content.find('</a>', a_start))
        else:
            print('a_tag not found')
"