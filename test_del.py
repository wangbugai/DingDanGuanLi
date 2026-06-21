import requests

s = requests.Session()
r = s.post('http://127.0.0.1:5000/login', json={'username':'admin','password':'admin123'})
token = r.json().get('token', '')
print('Token:', token[:20], '...')

# Test DELETE with header
headers = {'Authorization': 'Bearer ' + token}
r2 = requests.delete('http://127.0.0.1:5000/api/users/999', headers=headers)
print('DELETE non-existent:', r2.status_code, r2.text[:100])

# Test DELETE with URL param
r3 = requests.delete('http://127.0.0.1:5000/api/users/999?token=' + token)
print('DELETE URL param:', r3.status_code, r3.text[:100])

# Check users
r4 = requests.get('http://127.0.0.1:5000/api/users?token=' + token)
print('Users count:', r4.json()['count'])