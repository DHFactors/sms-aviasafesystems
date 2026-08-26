#!/usr/bin/env python3
import os

for html_file in ['login.html', 'safety.html']:
    path = os.path.join('public', html_file)
    with open(path, 'r') as f:
        content = f.read()
    # Replace the firebase script tag with version-busted version
    old = '<script src="/js/firebase.js"></script>'
    new = '<script src="/js/firebase.js?v=2.1.0"></script>'
    new_content = content.replace(old, new)
    with open(path, 'w') as f:
        f.write(new_content)
    print(html_file + ': cache-buster added')
"