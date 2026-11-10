"""解析 OSM pbf（中国 + 台湾），按类别导出名称（只保留含汉字的名称）。
用法：python3 parse_pbf.py raw/pbf/china.osm.pbf raw/pbf/taiwan.osm.pbf
输出：raw/osm_names/<kind>.tsv  （列：name \t 附加信息）
"""
import os, sys, re, collections
import osmium

OUT = os.path.join(os.path.dirname(__file__), "..", "raw", "osm_names")
os.makedirs(OUT, exist_ok=True)
HAN = re.compile(r"[\u4e00-\u9fff]")
NAME_KEYS = ("name:zh-Hans", "name:zh", "name", "name:zh-Hant", "official_name", "alt_name", "old_name", "short_name")

TOUR = {"attraction", "viewpoint", "museum", "theme_park", "zoo", "aquarium", "gallery"}
LEIS = {"park", "nature_reserve", "garden"}
NAT = {"peak", "water", "bay", "cape", "island", "volcano", "spring", "beach", "valley", "glacier", "ridge", "strait", "cliff"}
ROAD_SKIP = {"footway", "path", "steps", "cycleway", "bridleway", "corridor", "platform", "construction", "proposed"}


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.d = collections.defaultdict(collections.Counter)

    def names(self, t):
        out = []
        for k in NAME_KEYS:
            v = t.get(k)
            if v:
                for x in v.split(";"):
                    x = x.strip()
                    if x and HAN.search(x) and len(x) <= 30:
                        out.append(x)
        return out

    def add(self, kind, t, extra=""):
        for n in self.names(t):
            self.d[kind][(n, extra)] += 1

    def common(self, o, is_way=False):
        t = o.tags
        if not t:
            return
        hw = t.get("highway")
        if hw:
            if hw in ("services", "rest_area"):
                self.add("services", t, hw)
            elif is_way and hw not in ROAD_SKIP:
                self.add("road_" + ("motorway" if hw in ("motorway", "motorway_link") else
                                    "trunk" if hw in ("trunk", "trunk_link") else
                                    "major" if hw in ("primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link") else
                                    "minor"), t, t.get("ref", ""))
                ref = t.get("ref")
                if ref and hw in ("motorway", "trunk", "primary"):
                    self.d["road_ref"][(ref, hw)] += 1
        if t.get("barrier") == "toll_booth":
            self.add("toll", t)
        tour = t.get("tourism")
        if tour in TOUR:
            self.add("tourism", t, tour)
        lei = t.get("leisure")
        if lei in LEIS:
            self.add("tourism", t, lei)
        if t.get("historic"):
            self.add("historic", t, t.get("historic"))
        if t.get("boundary") in ("national_park", "protected_area"):
            self.add("tourism", t, "protected")
        pl = t.get("place")
        if pl:
            self.add("place_" + pl, t)
        rw = t.get("railway")
        if rw in ("station", "halt"):
            self.add("rail_station", t, t.get("station", ""))
        if t.get("public_transport") == "station":
            self.add("pt_station", t, t.get("train", "") + t.get("subway", ""))
        nat = t.get("natural")
        if nat in NAT:
            self.add("natural", t, nat)
        if t.get("waterway") in ("river", "canal"):
            self.add("natural", t, "river")
        if t.get("amenity") == "fuel" or t.get("shop") or t.get("amenity") in ("restaurant", "fast_food", "cafe", "bank"):
            b = t.get("brand:zh") or t.get("brand")
            if b and HAN.search(b):
                self.d["brand"][(b, t.get("shop") or t.get("amenity"))] += 1
            for k in ("brand:en",):
                b = t.get(k)
                if b:
                    self.d["brand_en"][(b, "")] += 1

    def node(self, n):
        self.common(n)

    def way(self, w):
        self.common(w, True)

    def relation(self, r):
        t = r.tags
        if t.get("type") == "route":
            route = t.get("route")
            if route in ("road", "train", "railway", "subway", "light_rail", "tram"):
                for n in self.names(t):
                    self.d["route_" + route][(n, t.get("ref", ""))] += 1
        else:
            self.common(r)


if __name__ == "__main__":
    h = H()
    for f in sys.argv[1:]:
        print("parsing", f, flush=True)
        h.apply_file(f, locations=False)
    for kind, c in h.d.items():
        with open(os.path.join(OUT, kind + ".tsv"), "w") as fo:
            for (n, extra), cnt in c.most_common():
                fo.write(f"{n}\t{extra}\t{cnt}\n")
        print(kind, len(c), flush=True)
