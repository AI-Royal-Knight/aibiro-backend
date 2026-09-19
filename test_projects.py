import requests

login_res = requests.post('http://localhost:8000/api/auth/login/', json={'email':'superadmin@gmail.com','password':'1fjw0676'})
token = login_res.json()['tokens']['access']

res = requests.get('http://localhost:8000/api/projects/', headers={'Authorization': f'Bearer {token}'})
print(res.json())
