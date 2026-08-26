import os

html_files = ['login.html', 'safety.html']
old_str = '<script src="/js/firebase.js"></script>'
new = '<script src="/js/firebase.js?v=2.1.0"></script>'

for html_file in html_files:
    path = os.path.join('public', html_file)
    with open(path, 'r') as f:
        content = f.read()
    new_content = content.replace(old_str, new)
    with open(path, 'w') as f:
        f.write(new_content)
    print(html_file + ': cache-buster added')
"