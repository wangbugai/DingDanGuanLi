import urllib.request
import sys

cookie = sys.argv[1] if len(sys.argv) > 1 else ''
url = sys.argv[2] if len(sys.argv) > 2 else 'http://xiyou.tongtiandai.com.cn/companymaintain/rolemanage?ref=addtabs'
outfile = sys.argv[3] if len(sys.argv) > 3 else 'page_py.html'

req = urllib.request.Request(url)
req.add_header('Cookie', cookie)
req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36')
req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
req.add_header('Accept-Language', 'zh-CN,zh;q=0.9')
req.add_header('Referer', 'http://xiyou.tongtiandai.com.cn/')

try:
    resp = urllib.request.urlopen(req, timeout=15)
    html = resp.read().decode('utf-8', errors='replace')
    with open(outfile, 'w', encoding='utf-8') as f:
        f.write(html)
    print('OK, length:', len(html))
    print('Need login:', '请登录后操作' in html)
except Exception as e:
    print('Error:', e)