import csv,collections,subprocess,os,zipfile
rows=list(csv.DictReader(open('files.csv')))
tr=[r['name'] for r in rows if r['name'].startswith('train/')]
c=collections.Counter(n.split('/')[1] for n in tr if n.endswith('ground_truth.csv'))
want=[n for n in tr if c[n.split('/')[1]]>=2 and (n.endswith('ground_truth.csv') or n.endswith('device_gnss.csv'))]
for i,n in enumerate(want):
    dst=os.path.join('data',os.path.dirname(n))
    if os.path.exists(os.path.join('data',n)): continue
    for tentativa in range(3):
        try:
            subprocess.run(['python3','-m','kaggle','competitions','download','-c','smartphone-decimeter-2022','-f',n,'-p','data','-q'],check=False,timeout=600); break
        except subprocess.TimeoutExpired:
            for f in os.listdir(dst) if os.path.isdir(dst) else []:
                if f.endswith('.zip') or f.endswith('.kaggle-partial'): os.remove(os.path.join(dst,f))
    if not os.path.isdir(dst): continue
    for z in [f for f in os.listdir(dst) if f.endswith('.zip')]:
        zipfile.ZipFile(os.path.join(dst,z)).extractall(dst); os.remove(os.path.join(dst,z))
    print(i+1,len(want),n,flush=True)
print('FIM',flush=True)
