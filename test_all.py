import urllib.request
import json
import http.cookiejar

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def get(url):
    r = opener.open(url, timeout=5)
    return r.status, r.read().decode('utf-8')

def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    r = opener.open(req, timeout=5)
    return json.loads(r.read().decode('utf-8'))

print('1. Test login page...')
status, html = get('http://127.0.0.1:5000/login')
print(f'   Login page: status={status}, has_title={("订单管理系统" in html)}')

print('2. Test login API...')
res = post('http://127.0.0.1:5000/login', {'username': 'admin', 'password': 'admin123'})
print(f'   Login: code={res.get("code")}, msg={res.get("msg")}')

print('3. Test index page...')
status, html = get('http://127.0.0.1:5000/')
print(f'   Index: status={status}, has_sidebar={("sidebar-menu" in html)}')

print('4. Test roles API...')
status, html = get('http://127.0.0.1:5000/api/roles')
res = json.loads(html)
print(f'   Roles: code={res.get("code")}, count={res.get("count")}')

print('5. Test users API...')
status, html = get('http://127.0.0.1:5000/api/users')
res = json.loads(html)
print(f'   Users: code={res.get("code")}, count={res.get("count")}')

print('6. Test orders API...')
status, html = get('http://127.0.0.1:5000/api/orders')
res = json.loads(html)
print(f'   Orders: code={res.get("code")}, count={res.get("count")}')

print('7. Test dashboard stats...')
status, html = get('http://127.0.0.1:5000/api/dashboard/stats')
res = json.loads(html)
print(f'   Stats: code={res.get("code")}, total_orders={res.get("data",{}).get("total_orders")}')

print('8. Test role manage page...')
status, html = get('http://127.0.0.1:5000/companymaintain/rolemanage')
print(f'   Role manage: status={status}, has_table={("listTable" in html)}')

print('9. Test admin manage page...')
status, html = get('http://127.0.0.1:5000/companymaintain/adminmanage')
print(f'   Admin manage: status={status}, has_agent={("agentModal" in html)}')

print('10. Test paidan page...')
status, html = get('http://127.0.0.1:5000/companypaidan/index')
print(f'   Paidan: status={status}, has_table={("listTable" in html)}')

print('\nAll tests passed!')