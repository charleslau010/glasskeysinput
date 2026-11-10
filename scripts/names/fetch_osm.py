"""从 OSM Overpass（mail.ru 镜像）按省抓取道路名、胡同弄堂、收费站、服务区、景点、自然村等名称。
输出：raw/osm/<kind>_<area>.tsv（列：name, name:zh, name:zh-Hans, name:zh-Hant, ref）
"""
import os, sys, time, urllib.request, urllib.parse

EP = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
OUT = os.path.join(os.path.dirname(__file__), "..", "raw", "osm")
os.makedirs(OUT, exist_ok=True)

PROV = "BJ TJ HE SX NM LN JL HL SH JS ZJ AH FJ JX SD HA HB HN GD GX HI CQ SC GZ YN XZ SN GS QH NX XJ".split()
AREAS = {p: f'area["ISO3166-2"="CN-{p}"]' for p in PROV}
AREAS.update({"HK": 'area["ISO3166-1"="HK"][admin_level=2]',
              "MO": 'area["ISO3166-1"="MO"][admin_level=2]',
              "TW": 'area["ISO3166-1"="TW"][admin_level=2]'})
HDR = '[out:csv(name,"name:zh","name:zh-Hans","name:zh-Hant",ref;false;"\t")][timeout:900][maxsize:2000000000];'

KINDS = {
    "roads": 'way["highway"]["name"](area.a);',
    "toll": 'nwr["barrier"="toll_booth"]["name"](area.a);',
    "services": 'nwr["highway"~"^(services|rest_area)$"]["name"](area.a);',
    "motorway": 'way["highway"~"^(motorway|trunk)$"](area.a);',
    "tourism": 'nwr["tourism"~"^(attraction|viewpoint|museum|theme_park|zoo|aquarium|gallery)$"]["name"](area.a);'
               'nwr["leisure"~"^(park|nature_reserve)$"]["name"](area.a);'
               'nwr["historic"]["name"](area.a);nwr["boundary"~"^(national_park|protected_area)$"]["name"](area.a);',
    "place": 'node["place"~"^(village|hamlet|neighbourhood|quarter|suburb|isolated_dwelling|locality|town)$"]["name"](area.a);',
    "rail": 'nwr["railway"~"^(station|halt)$"]["name"](area.a);nwr["public_transport"="station"]["name"](area.a);',
    "natural": 'nwr["natural"~"^(peak|water|bay|cape|island|volcano|cave_entrance|spring|beach|valley)$"]["name"](area.a);'
               'way["waterway"="river"]["name"](area.a);relation["waterway"="river"]["name"](area.a);',
}


def run(kind, area):
    fn = os.path.join(OUT, f"{kind}_{area}.tsv")
    if os.path.exists(fn) and os.path.getsize(fn) > 0:
        return "skip"
    q = HDR + AREAS[area] + "->.a;(" + KINDS[kind] + ");out tags;"
    import subprocess
    for attempt in range(3):
        try:
            body = subprocess.run(["curl", "-s", "-m", "1000", EP, "--data-urlencode", "data=" + q,
                                   "-A", "lexicon-builder/0.1"], capture_output=True).stdout
            if not body:
                raise RuntimeError("empty")
            if b"runtime error" in body[:2000] or b"<html" in body[:200]:
                raise RuntimeError(body[:300])
            open(fn, "wb").write(body)
            return f"ok {len(body)}"
        except Exception as e:
            err = str(e)[:200]
            time.sleep(15 * (attempt + 1))
    return "FAIL " + err


if __name__ == "__main__":
    kinds = sys.argv[1].split(",") if len(sys.argv) > 1 else list(KINDS)
    for kind in kinds:
        for area in AREAS:
            t = time.time()
            print(kind, area, run(kind, area), f"{time.time()-t:.0f}s", flush=True)
