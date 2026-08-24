with open('public/index.html', 'r', errors='replace') as f:
    c = f.read()
    
r1 = 'cursor-pointer' in c
r2 = 'toggleDemoModal' in c
r3 = 'demo-modal' in c
r4 = 'onclick' in c and 'toggleDemoModal' in c

print(f'1. cursor-pointer: {r1}')
print(f'2. toggleDemoModal: {r2}')
print(f'3. demo-modal ID: {r3}')
print(f'4. onclick + toggle: {r4}')

if r1 and r2 and r3 and r4:
    print('All checks passed! Ready to deploy.')
    print('git add public/index.html && git commit -m "fix: hero cta cursor and onclick" && firebase deploy --only hosting')
else:
    print('Some checks failed')