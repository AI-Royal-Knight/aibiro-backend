import requests
import json

login_res = requests.post('http://localhost:8000/api/auth/login/', json={'email':'superadmin@gmail.com','password':'1fjw0676'})
token = login_res.json()['tokens']['access']

# Fetch list
res = requests.get('http://localhost:8000/api/projects/', headers={'Authorization': f'Bearer {token}'})
projects = res.json().get('data', [])

if projects:
    pid = projects[0]['id']
    print(f"Fetching details for project {pid}")
    detail_res = requests.get(f'http://localhost:8000/api/projects/{pid}/', headers={'Authorization': f'Bearer {token}'})
    print(json.dumps(detail_res.json(), indent=2))
else:
    print("No projects found.")
