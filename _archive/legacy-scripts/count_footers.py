import os

old_text = 'A Project by Ghanshyam Acharya'
old_text2 = 'Ghanshyam Acharya'

count_old = 0
count_old2 = 0
total_html = 0

for root, dirs, files in os.walk('.'):
    if '.git' in root:
        continue
    for f in files:
        if f.endswith('.html'):
            total_html += 1
            try:
                with open(os.path.join(root, f), 'r', errors='replace') as fh:
                    content = fh.read()
                if old_text in content:
                    count_old += 1
                if old_text2 in content:
                    count_old2 += 1
            except:
                pass

print('Total HTML files: {}'.format(total_html))
print('Files with \"A Project by Ghanshyam Acharya\": {}'.format(count_old))
print('Files with \"Ghanshyam Acharya\": {}'.format(count_old2))
"