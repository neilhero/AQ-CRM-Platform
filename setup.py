import base64, os, tarfile, subprocess

b64 = open('/root/aq-crm.b64','r').read()
data = base64.b64decode(b64)
with open('/root/aq-crm.tar.gz','wb') as f: f.write(data)
with tarfile.open('/root/aq-crm.tar.gz') as t: t.extractall('/root/')

subprocess.run(['cp','-r','/root/aq-crm-deploy/backend/*','/opt/aq-crm/backend/'], shell=True)
subprocess.run(['cp','/root/aq-crm-deploy/frontend/index.html','/opt/aq-crm/frontend/'])

subprocess.run(['pip3','install','fastapi','uvicorn','sqlalchemy','pyjwt','pydantic','python-multipart'])

with open('/etc/systemd/system/aq-crm.service','w') as f:
    f.write('''[Unit]\nDescription=AQ CRM\nAfter=network.target\n[Service]\nType=simple\nWorkingDirectory=/opt/aq-crm/backend\nExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8097\nRestart=always\n[Install]\nWantedBy=multi-user.target\n''')

with open('/etc/nginx/sites-available/aq-crm','w') as f:
    f.write('''server {\n    listen 80;\n    root /opt/aq-crm/frontend;\n    index index.html;\n    location /api/ {\n        proxy_pass http://127.0.0.1:8097/api/;\n        proxy_set_header Host $host;\n    }\n    location / { try_files $uri /index.html; }\n}\n''')

subprocess.run(['ln','-sf','/etc/nginx/sites-available/aq-crm','/etc/nginx/sites-enabled/'])
subprocess.run(['rm','-f','/etc/nginx/sites-enabled/default'])
subprocess.run(['systemctl','daemon-reload'])
subprocess.run(['systemctl','enable','aq-crm'])
subprocess.run(['systemctl','restart','aq-crm'])
subprocess.run(['nginx','-t'])
subprocess.run(['systemctl','restart','nginx'])
print('DONE')
