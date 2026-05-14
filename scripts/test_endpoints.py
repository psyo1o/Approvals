import http.cookiejar, urllib.request, urllib.parse, json, sys

BASE = 'http://localhost:8000'
ADMIN = ('admin', 'admin1234!')

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# login
login_url = BASE + '/login'
post_data = urllib.parse.urlencode({'username': ADMIN[0], 'password': ADMIN[1]}).encode('utf-8')
req = urllib.request.Request(login_url, data=post_data, method='POST')
try:
    resp = opener.open(req, timeout=10)
    final_url = resp.geturl()
    print('login final url:', final_url)
    print('cookies:', [c.name+"="+c.value for c in cj])
except Exception as e:
    print('login error', e)
    sys.exit(1)

# helper to GET
def get(path):
    url = BASE + path
    req = urllib.request.Request(url)
    try:
        r = opener.open(req, timeout=10)
        content = r.read(1000)
        print(path, '->', r.getcode(), 'len', len(content))
        # print first 300 bytes
        print(content.decode('utf-8', errors='replace')[:300])
    except urllib.error.HTTPError as he:
        print(path, 'HTTPError', he.code, he.reason)
    except Exception as e:
        print(path, 'error', e)

# test endpoints
get('/org')
get('/calendar')
# api events JSON
try:
    req = urllib.request.Request(BASE + '/api/events')
    r = opener.open(req, timeout=10)
    data = r.read()
    try:
        arr = json.loads(data)
        print('/api/events ->', len(arr), 'items')
    except Exception as e:
        print('/api/events -> non-json', e)
except Exception as e:
    print('/api/events error', e)

# try creating an event via POST form (submit as query params since form parsing is limited)
create_url = BASE + '/api/events?title=테스트일정&start_time=2026-03-20T09:00:00&end_time=2026-03-20T10:00:00'
try:
    r = opener.open(create_url, data=b'', timeout=10)
    print('create event ->', r.getcode(), r.geturl())
except Exception as e:
    print('create event error', e)

# re-fetch events
try:
    req = urllib.request.Request(BASE + '/api/events')
    r = opener.open(req, timeout=10)
    arr = json.loads(r.read())
    print('/api/events after create ->', len(arr), 'items')
    if arr:
        print('first event:', arr[0])
except Exception as e:
    print('/api/events fetch error', e)
