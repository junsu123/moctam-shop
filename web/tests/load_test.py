# Đo tải sơ bộ NFR-03: python3 tests/load_test.py (sửa B= thành địa chỉ môi trường thử; tạm tắt rate_limit khi đo)
CODES={}
import urllib.error, json, re, statistics, threading, time, urllib.request, http.cookiejar, uuid
B='http://127.0.0.1:8080'
def p95(xs): xs=sorted(xs); return xs[int(len(xs)*0.95)-1]
def read_worker(res, n):
    for i in range(n):
        for u in ['/', '/tra-tui-loc.html', '/tim-kiem.html?q=tra+gung', '/bot-ngu-coc-25-loai-hat.html']:
            t=time.perf_counter(); urllib.request.urlopen(B+u).read(); res.append((time.perf_counter()-t)*1000)
def order_worker(res, idx, n):
    cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    html=op.open(B+'/dat-hang.html').read().decode(); tok=re.search(r'name="csrf-token" content="([^"]+)"',html).group(1)
    for i in range(n):
        items=[{"sku_id":2,"qty":1},{"sku_id":5,"qty":1}]
        q=json.loads(op.open(urllib.request.Request(B+'/api/quote',data=json.dumps({"items":items,"province":"Hà Nội"}).encode(),headers={"Content-Type":"application/json"})).read())['quote']
        body={"items":items,"payment_method":"cod","quote_token":q['quote_token'],"customer":{"name":"Tải Thử","phone":"03%08d"%(idx*100+i),"province":"Hà Nội","address":"1 Đường Thử Tải, P1"}}
        t=time.perf_counter()
        try:
            r=op.open(urllib.request.Request(B+'/api/orders',data=json.dumps(body).encode(),headers={"Content-Type":"application/json","X-CSRF-Token":tok,"Idempotency-Key":"load_"+uuid.uuid4().hex})); r.read(); CODES['201']=CODES.get('201',0)+1
        except urllib.error.HTTPError as e:
            CODES[json.loads(e.read())['error']['code']]=CODES.get(json.loads('{}') and '' or 'x',0); CODES.setdefault('err',[]).append(e.code)
        res.append((time.perf_counter()-t)*1000)
for name,fn,args in [('Đọc danh mục/trang sản phẩm',read_worker,(10,)),('Tạo đơn',None,None)]:
    res=[]; th=[]
    for k in range(20):
        th.append(threading.Thread(target=(read_worker if fn else order_worker),args=((res,)+args) if fn else (res,k,3)))
    t0=time.time(); [x.start() for x in th]; [x.join() for x in th]
    print(CODES if not fn else '', f"{name}: {len(res)} yêu cầu, 20 luồng đồng thời, p50={statistics.median(res):.0f}ms p95={p95(res):.0f}ms max={max(res):.0f}ms ({time.time()-t0:.1f}s)")
