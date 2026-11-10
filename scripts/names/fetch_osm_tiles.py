"""OSM 分块自适应抓取（mail.ru Overpass 镜像）。
中国（含港澳台）范围按 4°x4° 切块，超时/失败则四分递归，最小 0.25°。
一次查询同时取：道路名、收费站、服务区、景点、居民点、车站、自然地物。
输出：raw/osm_tiles/<s>_<w>_<n>_<e>.tsv
"""
import os, sys, subprocess, time
from concurrent.futures import ThreadPoolExecutor

EP = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
OUT = os.path.join(os.path.dirname(__file__), "..", "raw", "osm_tiles")
os.makedirs(OUT, exist_ok=True)

COLS = 'name,"name:zh","name:zh-Hans",highway,barrier,tourism,place,railway,leisure,historic,natural,waterway,ref'
BODY = ('way["highway"]["name"](area.a)(B);'
        'nwr["barrier"="toll_booth"]["name"](area.a)(B);'
        'nwr["highway"~"^(services|rest_area)$"]["name"](area.a)(B);'
        'way["highway"~"^(motorway|trunk)$"]["ref"](area.a)(B);'
        'nwr["tourism"~"^(attraction|viewpoint|museum|theme_park|zoo|aquarium|gallery)$"]["name"](area.a)(B);'
        'nwr["leisure"~"^(park|nature_reserve|garden)$"]["name"](area.a)(B);'
        'nwr["historic"]["name"](area.a)(B);'
        'node["place"]["name"](area.a)(B);'
        'nwr["railway"~"^(station|halt)$"]["name"](area.a)(B);'
        'nwr["natural"~"^(peak|water|bay|cape|island|volcano|spring|beach|valley|glacier)$"]["name"](area.a)(B);'
        'way["waterway"="river"]["name"](area.a)(B);')


def query(s, w, n, e, tmo):
    bb = f"{s},{w},{n},{e}"
    q = (f'[out:csv({COLS};false;"\t")][timeout:{tmo}][maxsize:1073741824];'
         '(' + BODY.replace("(area.a)(B)", f"({bb})") + ');out tags;')
    r = subprocess.run(["curl", "-s", "-m", str(tmo + 30), EP, "--data-urlencode", "data=" + q,
                        "-A", "lexicon-builder/0.1", "-w", "\n__HTTP%{http_code}"], capture_output=True)
    body = r.stdout
    tail = body[-20:]
    if b"__HTTP200" not in tail:
        return None
    body = body[: body.rfind(b"\n__HTTP")]
    if body.lstrip().startswith(b"<") or b"runtime error" in body[:500] or b"Timeout" in body[:500]:
        return None
    return body


def fetch(tile):
    s, w, n, e = tile
    fn = os.path.join(OUT, f"{s}_{w}_{n}_{e}.tsv")
    if os.path.exists(fn):
        return []
    size = n - s
    tmo = 180
    for attempt in range(2):
        body = query(s, w, n, e, tmo)
        if body is not None:
            open(fn, "wb").write(body)
            print(f"ok {tile} {len(body)}", flush=True)
            return []
        time.sleep(5)
    if size <= 0.25:
        print(f"FAIL {tile}", flush=True)
        open(fn + ".fail", "w").write("")
        return []
    h = size / 2
    print(f"split {tile}", flush=True)
    return [(s, w, s + h, w + h), (s, w + h, s + h, e), (s + h, w, n, w + h), (s + h, w + h, n, e)]


if __name__ == "__main__":
    tiles = [(lat, lon, lat + 2, lon + 2) for lat in range(18, 54, 2) for lon in range(73, 135, 2)]  # 不用 area 过滤（太慢），后处理按含汉字过滤
    tiles.append((54, 120, 56, 128))  # 漠河以北
    tiles.append((14, 108, 18, 120))  # 南海北部（西沙等）
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    with ThreadPoolExecutor(workers) as ex:
        while tiles:
            nxt = []
            for res in ex.map(fetch, tiles):
                nxt.extend(res)
            tiles = nxt
    print("DONE", flush=True)
