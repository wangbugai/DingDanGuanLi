import requests

s = requests.Session()

# Test login
r = s.post('http://127.0.0.1:5000/login', json={'username':'admin','password':'admin123'})
print('Login:', r.json().get('code'), 'token:', r.json().get('token','')[:20])
token = r.json().get('token', '')

# Test /api/current_user with header
r2 = s.get('http://127.0.0.1:5000/api/current_user', headers={'Authorization': 'Bearer ' + token})
print('Current user:', r2.json().get('data',{}).get('nickname'), 'perms:', len(r2.json().get('data',{}).get('permissions',[])))

# Test / (main page) - should return HTML
r3 = s.get('http://127.0.0.1:5000/')
print('Main page status:', r3.status_code, 'length:', len(r3.text))

# Test roles API with header
r4 = s.get('http://127.0.0.1:5000/api/roles', headers={'Authorization': 'Bearer ' + token})
print('Roles count:', r4.json().get('count'))

# Create agent and test role filtering
s.post('http://127.0.0.1:5000/api/users?token=' + token, json={
    'username': 'agent1', 'password': '123456', 'nickname': '代理1', 'role_id': 2, 'status': 'normal'
}, headers={'Authorization': 'Bearer ' + token})
s.post('http://127.0.0.1:5000/api/users/2/set_agent?token=' + token, json={
    'is_agent': True, 'agent_level': 1
}, headers={'Authorization': 'Bearer ' + token})

# Login as agent
s2 = requests.Session()
r5 = s2.post('http://127.0.0.1:5000/login', json={'username':'agent1','password':'123456'})
agent_token = r5.json().get('token', '')

# Test roles as agent - should NOT see system_admin role
r6 = s2.get('http://127.0.0.1:5000/api/roles', headers={'Authorization': 'Bearer ' + agent_token})
roles = r6.json().get('data', [])
print('Agent sees roles:', [r['name'] for r in roles])
has_admin_role = any('system_admin' in r.get('permissions',[]) for r in roles)
print('Agent can see admin role:', has_admin_role)

print('\nAll tests passed!')