"""输入法联想词库构建脚本。
读取 raw/ 下的开源数据 + scripts/curated/ 人工整理词表，清洗、繁转简、去重，输出到 词库/ 目录（Markdown）。
"""
import os, re, csv, glob, json, collections
import opencc
from pypinyin import lazy_pinyin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
CUR = os.path.join(ROOT, "scripts", "curated")
OUT = os.path.join(ROOT, "词库")
os.makedirs(OUT, exist_ok=True)
T2S = opencc.OpenCC("t2s")
DATE = "2026-10-22"

HAN = re.compile(r"[\u3400-\u9fff]")
KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
BAD = re.compile(r"[\{\}\[\]<>=|\\@#\t\n？?!！*※■□○●◎☆★…_^~`$%]|https?:|Category|Template|File:|Q\d{3,}$|^\W")
OTHER_SCRIPT = re.compile(r"[\u0400-\u04ff\u0600-\u06ff\u0e00-\u0e7f\u0f00-\u0fff\u1800-\u18af\u0900-\u097f\u1000-\u109f\u0590-\u05ff]")
PAREN = re.compile(r"\s*[（(][^（）()]{0,30}[）)]\s*$")
STATS = collections.OrderedDict()   # 文件 -> 词条数


def clean(s, keep_trad=False, allow_latin=False, maxlen=30):
    if not s:
        return None
    s = s.replace("\u200b", "").replace("\u3000", " ").replace("\xa0", " ").strip().strip("\"'“”‘’「」『』《》")
    s = PAREN.sub("", s).strip()
    s = re.sub(r"^[（(][^（）()]{0,6}[）)]", "", s).strip()
    s = re.sub(r"[（(][^（）()]{0,20}[）)]", "", s).strip()
    s = re.sub(r"[“”\"‘’「」『』《》]", "", s).strip()
    s = s.strip("·・-－— ")
    s = re.sub(r"\s+", " ", s)
    if not s or BAD.search(s) or re.search(r"[，。；：！？]", s) or s.count("（") != s.count("）") or s.count("(") != s.count(")"):
        return None
    if OTHER_SCRIPT.search(s):
        # 混排（中文 + 蒙/藏/维等）时只保留含汉字的片段
        toks = [t for t in s.split(" ") if HAN.search(t) and not OTHER_SCRIPT.search(t)]
        if not toks:
            return None
        s = toks[0]
    if not keep_trad:
        s = T2S.convert(s)
    if len(s) < 2 or len(s) > maxlen:
        return None
    if KANA.search(s) or HANGUL.search(s):
        return None
    if not HAN.search(s) and not allow_latin:
        return None
    if not HAN.search(s):
        if re.fullmatch(r"\d{3,6}", s):
            return s
        if not re.search(r"[A-Za-z]", s) or len(s) > 40:
            return None
    return s


NOISY = re.compile(r"\d|[A-Za-z]|[-－/、,，;；:：•\s.]|(临时|规划|待建|在建)路$|^(老路|辅路|便道)$|号(院|楼|门|口|路|线|街)|支弄|弄\d|衖")


def strict(names):
    """OSM/众包来源：去掉含数字、字母、分隔符等噪声的名称。"""
    return [n for n in names if n and not NOISY.search(n)]


def han_part(s):
    """OSM 名称常见 '中文 English' 双语，取中文段。"""
    if not s:
        return s
    if HAN.search(s) and re.search(r"[A-Za-z]{3,}", s) and " " in s:
        toks = [t for t in s.split(" ") if HAN.search(t)]
        if toks:
            return toks[0]
    return s


def pykey(w):
    try:
        return ("".join(lazy_pinyin(w[:3])).lower(), w)
    except Exception:
        return (w, w)


class Book:
    """一个 md 文件：多个小节，小节内去重 + 跨小节去重。"""

    def __init__(self, path, title, intro, global_seen=None, sort=True):
        self.path, self.title, self.intro = path, title, intro
        self.sections = collections.OrderedDict()
        self.seen = global_seen if global_seen is not None else set()
        self.sort = sort

    def add(self, sec, words, sort=None, **kw):
        lst = self.sections.setdefault(sec, ([], self.sort if sort is None else sort))[0]
        for w in words:
            w = clean(w, **kw) if not kw.get("raw") else w
            if w and w not in self.seen:
                self.seen.add(w)
                lst.append(w)

    def total(self):
        return sum(len(v[0]) for v in self.sections.values())

    def write(self):
        n = self.total()
        lines = [f"# {self.title}", "", f"> 词条数：**{n:,}**　|　整理日期：{DATE}　|　每行一个词，可直接导入输入法自定义词库", "", self.intro.strip(), ""]
        lines.append("## 目录")
        lines.append("")
        for sec, (lst, _) in self.sections.items():
            if lst:
                lines.append(f"- {sec}（{len(lst):,}）")
        lines.append("")
        for sec, (lst, srt) in self.sections.items():
            if not lst:
                continue
            if srt:
                lst = sorted(lst, key=pykey)
            lines.append(f"## {sec}（{len(lst):,}）")
            lines.append("")
            lines.append("```text")
            lines.extend(lst)
            lines.append("```")
            lines.append("")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        open(self.path, "w", encoding="utf-8").write("\n".join(lines))
        STATS[os.path.relpath(self.path, OUT)] = n
        print(f"{os.path.relpath(self.path, OUT)}  {n:,}", flush=True)
        return n


# ---------------- 读取工具 ----------------

def read_lines(p):
    if not os.path.exists(p):
        return []
    return [l.rstrip("\r\n") for l in open(p, encoding="utf-8", errors="ignore")]


def wd(name):
    return read_lines(os.path.join(RAW, "wd", name + ".txt"))


def osm(kind, mincnt=1):
    out = []
    for l in read_lines(os.path.join(RAW, "osm_names", kind + ".tsv")):
        p = l.split("\t")
        if len(p) >= 3 and int(p[2] or 0) >= mincnt:
            out.append((han_part(p[0]), p[1]))
    return out


def curated(fname):
    """返回 OrderedDict 小节 -> 词列表"""
    secs = collections.OrderedDict()
    cur = "其他"
    for l in read_lines(os.path.join(CUR, fname)):
        l = l.strip()
        if not l or l.startswith("# "):
            continue
        if l.startswith("## "):
            cur = l[3:].strip()
            continue
        for w in l.split("｜"):
            w = w.strip()
            if w:
                secs.setdefault(cur, []).append(w)
    return secs


def wiki(name):
    p = os.path.join(RAW, "zhwiki", name + ".wiki")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


LINK = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|([^\[\]]+))?\]\]")


def wiki_links(txt):
    out = []
    for a, b in LINK.findall(txt):
        if ":" in a:
            continue
        out.append(a.strip())
        if b:
            out.append(b.strip())
    return out


def strip_wiki(s):
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = LINK.sub(lambda m: m.group(2) or m.group(1), s)
    s = re.sub(r"'''?|<[^>]+>", "", s)
    return s.strip()


def wiki_cells(txt):
    out = []
    for l in txt.split("\n"):
        if l.startswith("|") and not l.startswith("|-") and not l.startswith("|}") and not l.startswith("|+"):
            for c in re.split(r"\|\|", l[1:]):
                if "=" in c.split("|")[0] and "|" in c and "[[" not in c.split("|")[0]:
                    c = c.split("|", 1)[1]
                c = re.sub(r"<br\s*/?>|\]\]\s*[、，,；;]?\s*\[\[", lambda m: "]]\n[[" if "]" in m.group(0) else "\n", c)
                for part in c.split("\n"):
                    part = strip_wiki(part)
                    part = re.sub(r"（.*?）|\(.*?\)", "", part).strip()
                    if part:
                        out.append(part)
    return out


# ---------------- 行政区划（统计用区划代码） ----------------
prov = {r["code"]: r["name"] for r in csv.DictReader(open(os.path.join(RAW, "adm_provinces.csv")))}
cities = list(csv.DictReader(open(os.path.join(RAW, "adm_cities.csv"))))
areas = list(csv.DictReader(open(os.path.join(RAW, "adm_areas.csv"))))
streets = list(csv.DictReader(open(os.path.join(RAW, "adm_streets.csv"))))
city_name = {r["code"]: r["name"] for r in cities}
area_name = {r["code"]: r["name"] for r in areas}
ADMIN = set(prov.values()) | set(city_name.values()) | set(area_name.values()) | {r["name"] for r in streets}


def short_admin(n):
    """生成行政区简称：广东省->广东，深圳市->深圳，宝安区->宝安（仅 >=2 字时）。"""
    out = []
    for suf in ("维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "特别行政区", "省", "市"):
        if n.endswith(suf) and len(n) - len(suf) >= 2:
            out.append(n[: -len(suf)])
            break
    m = re.match(r"(.{2,}?)(土家族苗族|苗族侗族|布依族苗族|哈尼族彝族|傣族景颇族|藏族羌族|蒙古族藏族|朝鲜族|[\u4e00-\u9fff]{1,4}族)?(自治州|自治县|自治旗|地区|盟|县|区|旗)$", n)
    if m and not out and n[-1] in "县区旗州盟" and len(m.group(1)) >= 2 and m.group(1) not in ("市辖", "城", "郊", "矿", "新"):
        out.append(m.group(1))
    return out


VSUF = [("社区居民委员会", "社区"), ("社区居委会", "社区"), ("村民委员会", "村"), ("村委会", "村"),
        ("居民委员会", "社区"), ("居委会", "社区"), ("嘎查委员会", "嘎查"), ("牧委会", "牧场"), ("家委会", ""), ("渔委会", "")]


def clean_village(n):
    n = n.strip()
    if "虚拟" in n:
        return None
    n = re.sub(r"[（(][^）)]*[）)]$", "", n)
    for suf, rep in VSUF:
        if n.endswith(suf):
            base = n[: -len(suf)]
            if rep and base.endswith(rep):
                return base
            if rep == "社区" and base.endswith(("村", "街", "路", "里", "巷", "苑", "园", "城", "区")):
                return base if len(base) >= 2 else n
            return base + rep if len(base) >= 1 else n
    return n


def build_places():
    seen = set()
    b = Book(os.path.join(OUT, "01_地名", "01-00_全国省市县乡_行政区划.md"), "中国地名 · 省 / 市 / 区县 / 乡镇街道（含简称）",
             "数据来源：国家统计局统计用区划代码（modood/Administrative-divisions-of-China 整理版，2023 年版五级区划）。"
             "同时自动生成常用简称（如 广东省→广东、宝安区→宝安）。港澳台见 `01-70_港澳台地名.md`。", seen, sort=False)
    b.add("省级行政区（含简称）", [x for p in prov.values() for x in [p] + short_admin(p)])
    b.add("区域 / 城市群 / 别称",
          ["京津冀", "长三角", "珠三角", "粤港澳大湾区", "大湾区", "成渝", "成渝双城经济圈", "关中平原", "中原城市群", "长江中游城市群", "北部湾", "东北三省", "西北五省", "江浙沪", "江浙沪包邮区", "北上广深", "北上广", "新一线城市", "一线城市", "二线城市", "三四线城市", "华北", "华东", "华南", "华中", "西南", "西北", "东北", "港澳台", "两岸三地", "海峡两岸", "闽南", "潮汕", "客家", "江南", "岭南", "塞北", "江北", "苏南", "苏北", "皖南", "皖北", "浙东", "浙西", "湘西", "鄂西", "川西", "滇西", "藏南", "陕北", "陕南", "关中", "晋中", "晋北", "豫东", "鲁西南", "胶东", "辽东", "辽西", "雄安新区", "浦东新区", "滨海新区", "两江新区", "前海", "横琴", "南沙", "河套", "海南自贸港"])
    by_prov = collections.defaultdict(list)
    for c in cities:
        by_prov[c["provinceCode"]].append(c)
    for pc, pn in prov.items():
        ws = []
        for c in by_prov[pc]:
            if c["name"] not in ("市辖区", "县", "省直辖县级行政区划", "自治区直辖县级行政区划"):
                ws += [c["name"]] + short_admin(c["name"])
        for a in areas:
            if a["provinceCode"] == pc and a["name"] not in ("市辖区",):
                ws += [a["name"]] + short_admin(a["name"])
        b.add(f"{pn} · 地市与区县", ws)
    for pc, pn in prov.items():
        ws = []
        for s in streets:
            if s["provinceCode"] == pc:
                n = s["name"]
                ws.append(n)
                for suf in ("街道办事处", "街道", "镇", "乡", "苏木"):
                    if n.endswith(suf) and len(n) - len(suf) >= 2 and suf not in ("镇", "乡"):
                        ws.append(n[: -len(suf)])
                        break
        b.add(f"{pn} · 乡镇 / 街道", ws)
    b.write()

    # 村 / 社区：按省拆分
    vil = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in csv.DictReader(open(os.path.join(RAW, "adm_villages.csv"))):
        v = clean_village(r["name"])
        if v:
            vil[r["provinceCode"]][r["areaCode"]].append(v)
    for pc, pn in prov.items():
        vb = Book(os.path.join(OUT, "01_地名", "村居社区", f"{pc}_{pn}.md"), f"{pn} · 村 / 社区（按区县）",
                  "数据来源：国家统计局统计用区划代码（村级）。已去掉“村民委员会 / 居民委员会”等后缀，保留“××村 / ××社区”形式，并去除“虚拟社区”。",
                  set(), sort=False)
        for ac in sorted(vil[pc]):
            an = area_name.get(ac, ac)
            cn = city_name.get(ac[:4], "")
            vb.add(f"{cn}{an}" if cn and cn != an and cn != "市辖区" else an, vil[pc][ac])
        vb.write()
        seen |= vb.seen

    # 胡同 / 弄堂 / 里巷
    hb = Book(os.path.join(OUT, "01_地名", "01-80_胡同_弄堂_里巷_老街.md"), "胡同 / 弄堂 / 里弄 / 巷 / 老街",
              "来源：人工整理的知名胡同与弄堂 + Wikidata（胡同类条目）+ 中文维基《北京胡同列表》+ OpenStreetMap 全国道路名中以“胡同 / 斜街 / 夹道 / 弄 / 里 / 坊 / 巷”结尾的路名（去掉含门牌数字的名称）。", seen)
    cur = curated("01_places.txt")
    for k, v in cur.items():
        if "胡同" in k or "弄堂" in k or "老街" in k:
            hb.add(k, v)
    hb.add("北京胡同（Wikidata / 维基百科）", wd("g_hutong") + [x for x in wiki_links(wiki("北京胡同列表")) if re.search(r"(胡同|条|街|巷|夹道|营|里)$", x)])
    rx = {"胡同 / 斜街 / 夹道（OSM）": r"(胡同|斜街|夹道)$", "弄 / 里弄 / 弄堂（OSM）": r"(弄|弄堂|里弄)$",
          "里 / 坊（OSM）": r"[^公]里$|坊$", "巷（OSM）": r"巷$"}
    roads = [n for k in ("road_minor", "road_major") for n, _ in osm(k)]
    for sec, r in rx.items():
        hb.add(sec, [n for n in strict(roads) if re.search(r, T2S.convert(n)) and not re.search(r"[一二三四五六七八九十百]+[段弄巷号]", n)])
    hb.write()

    # 港澳台
    tb = Book(os.path.join(OUT, "01_地名", "01-70_港澳台地名.md"), "中国香港 / 中国澳门 / 中国台湾 地名",
              "来源：人工整理（港澳分区、堂区、常用地区名；台湾县市与乡镇市区）+ Wikidata（台湾村里、港澳地物）。简体为主，同时保留繁体写法便于两岸输入。", set())
    for k, v in cur.items():
        if k.startswith(("中国香港", "中国澳门", "中国台湾")):
            tb.add(k, v)
            tb.add(k + "（繁体写法）", v, keep_trad=True)
    tb.add("中国台湾 · 村里 / 乡镇区（Wikidata）", [x for x in strict(wd("g_tw_admin") + wd("g_tw_place")) if not re.search(r"选举区|選舉區|医院|醫院|营区|營區|学校|學校|公司|大学|大學|议员|議員", x) and re.search(r"(里|村|乡|鄉|镇|鎮|区|區|市|县|縣|社|部落|庄|莊|寮|厝|坑|埔|仔|湾|灣|港|山|街|屿|嶼|岛|島|城|厝|林|寮|脚|腳|头|頭|尾|口)$", x)])
    tb.add("港澳地物（Wikidata）", wd("g_hkmo_place"))
    tb.write()
    seen |= tb.seen

    # OSM 小地名补充
    ob = Book(os.path.join(OUT, "01_地名", "01-90_自然村_小地名_片区_OSM补充.md"), "自然村 / 小地名 / 片区 / 岛屿（OpenStreetMap 补充）",
              "来源：OpenStreetMap 中国及台湾数据（2026-10-21 快照）中 place=* 节点名称，已去除与统计区划重复的词、繁转简。包含自然村、屯、组、片区、街区、岛屿、礁等，适合补充生僻地名联想。", seen)
    STOP = {"牧民", "民居", "县城", "建筑", "村庄", "居民点", "新村", "小区", "住宅", "村委会", "停车场", "公厕", "厕所", "学校", "无名", "北门", "南门", "东门", "西门", "大门"}
    groups = [("城镇 / 乡镇（OSM）", ["place_town", "place_city", "place_county", "place_district", "place_township", "place_municipality", "place_banner", "place_league"]),
              ("村 / 自然村（OSM）", ["place_village"]), ("屯 / 组 / 小自然村（OSM）", ["place_hamlet", "place_isolated_dwelling", "place_farm"]),
              ("片区 / 街区 / 社区（OSM）", ["place_suburb", "place_quarter", "place_neighbourhood", "place_city_block", "place_square", "place_subdistrict", "place_community", "place_borough"]),
              ("小地名 / 地块（OSM）", ["place_locality", "place_region", "place_plot", "place_field", "place_polder"]),
              ("岛屿 / 礁 / 群岛（OSM）", ["place_island", "place_islet", "place_archipelago", "place_atoll", "place_peninsula"])]
    for sec, kinds in groups:
        ob.add(sec, [n for n in strict([n for k in kinds for n, _ in osm(k)]) if n not in STOP and not re.search(r"道班|工班", n)])
    ob.write()
    return seen


# ---------------- 旅游景区 ----------------

def build_scenic():
    b = Book(os.path.join(OUT, "02_旅游景区.md"), "中国（含港澳台）旅游风景区 / 景点",
             "来源：中文维基《国家5A级旅游景区》《国家4A级旅游景区》《国家级风景名胜区》《中华人民共和国世界遗产列表》（表格解析）、"
             "Wikidata（全国重点文物保护单位、中国境内景点/山/湖/寺庙/公园/博物馆等）、OpenStreetMap（tourism / historic / leisure=park / natural 名称）、人工整理港澳台热门景点。"
             "已剔除与行政区划同名的词。", set())
    cur = curated("02_scenic.txt")
    for k, v in cur.items():
        b.add(k, v)

    ADM_END = re.compile(r"(省|市|县|自治州|盟|旗|地区|(?<![景游览旅区护假园化街胜心])区)$")

    def table(name):
        out = []
        for c in wiki_cells(wiki(name)):
            c = T2S.convert(c).strip("·・ ")
            if re.search(r"\d", c) or c in ADMIN or ADM_END.search(c) or len(c) > 28 or (re.match(r"^.{2,3}(省|自治区)", c) and len(c) <= 8) or re.search(r"(取消|摘牌|批准|公布|年份|名称|所在地|地区|备注|序号|编号|级别|类别)", c):
                continue
            out.append(c)
        return out
    b.add("国家5A级旅游景区", [x for x in table("国家5A级旅游景区") if x not in ADMIN])
    b.add("国家级风景名胜区", [x for x in table("国家级风景名胜区") if x not in ADMIN])
    b.add("世界遗产（中国）", [x for x in table("中華人民共和國世界遺產列表") if x not in ADMIN])
    b.add("国家4A级旅游景区", [x for x in table("国家4A级旅游景区") if x not in ADMIN])
    b.add("全国重点文物保护单位（Wikidata）", wd("scenic_heritage"))
    b.add("景点 / 名山 / 湖泊 / 寺庙 / 公园（Wikidata）", [x for x in wd("scenic_cn") if clean(x) not in ADMIN])
    STOP = re.compile(r"^(公园|广场|观景台|景点|停车场|厕所|游客中心|售票处|入口|出口|大门|东门|西门|南门|北门|纪念碑|雕塑|凉亭|亭子|长廊|水池|喷泉|花园|小花园|游乐场|儿童乐园|观景点|观景平台|博物馆|纪念馆|美术馆|展览馆|动物园|植物园)$")
    tour = [(n, e) for n, e in osm("tourism") if n and not NOISY.search(n)]
    b.add("博物馆 / 美术馆 / 纪念馆（OSM）", [n for n, e in tour if e in ("museum", "gallery") and n and not STOP.match(n)])
    b.add("主题乐园 / 动物园 / 水族馆（OSM）", [n for n, e in tour if e in ("theme_park", "zoo", "aquarium") and n and not STOP.match(n)])
    b.add("景点 / 观景点（OSM）", [n for n, e in tour if e in ("attraction", "viewpoint") and n and not STOP.match(n)])
    b.add("公园 / 自然保护区 / 园林（OSM）", [n for n, e in tour if e in ("park", "nature_reserve", "garden", "protected") and n and not STOP.match(n)])
    b.add("古迹 / 遗址 / 文物（OSM）", [n for n in strict([n for n, e in osm("historic")]) if not STOP.match(n) and len(n) >= 3])
    b.add("山峰 / 湖泊 / 河流 / 海湾 / 海滩（OSM + Wikidata）", wd("g_cn_mountain_river") + [n for n, e in osm("natural") if n and not NOISY.search(n) and e in ("peak", "volcano", "bay", "beach", "cape", "glacier", "valley", "spring", "water", "river", "island", "strait")])
    b.write()


# ---------------- 道路 ----------------

def expressway_variants(n, stem_ok=True):
    out = [n]
    n2 = T2S.convert(n)
    m = re.match(r"^(.{2,10}?)(高速公路|高速)(.{0,4})$", n2)
    if m:
        stem, tail = m.group(1), m.group(3)
        stem = stem.replace("－", "-").replace("—", "-")
        if "-" in stem:  # 京港-澳 之类的全称
            pass
        out += [stem + "高速" + tail, stem + "高速公路" + tail]
        if stem_ok and len(stem) >= 2 and not re.search(r"(绕城|环线|机场|连接线|支线|联络线|复线|段|城市|外环|内环|过境)$", stem) and tail == "":
            out.append(stem)
    return out


def build_roads():
    seen = set()
    cur = curated("03_roads.txt")
    # 高速 / 快速路
    b = Book(os.path.join(OUT, "03_道路交通", "03-1_高速公路_快速路_国省道.md"), "高速公路 / 快速路 / 国道省道（含简称与编号）",
             "来源：人工整理（国家高速 G 编号主线与简称、港澳台快速公路）+ 中文维基《中华人民共和国国家高速公路网》《中華民國國道》《香港幹線編號系統》+ Wikidata（中国高速公路条目）+ OpenStreetMap（motorway / trunk 名称、ref 编号、road route 关系）。"
             "对“××高速公路”自动补齐“××高速”“××”三种写法（如 京港澳高速公路 / 京港澳高速 / 京港澳）。", seen)
    for k, v in cur.items():
        if ("高速" in k or "国道" in k or "快速" in k or "港澳台" in k) and "收费" not in k:
            vv = [x for w in v for x in expressway_variants(w)]
            b.add(k, vv, allow_latin=True)
    wk = [x for x in wiki_links(wiki("中华人民共和国国家高速公路网")) if re.search(r"(高速|高速公路|环线)$", x)]
    b.add("国家高速公路（维基百科）", [x for w in wk for x in expressway_variants(w)])
    b.add("中国台湾国道 / 快速公路（维基百科）", [x for x in wiki_links(wiki("中華民國國道")) + wiki_cells(wiki("中華民國國道")) if re.fullmatch(r"(國道.{1,3}號.{0,3}|.{2,10}(高速公路|快速公路|快速道路|交流道))", x) and not re.search(r"局|系統|工程|電子|國道.號國道|至", x)])
    b.add("中国香港干线 / 快速公路（维基百科）", [x for x in wiki_links(wiki("香港幹線編號系統")) if re.search(r"(公路|道|隧道|大橋|大桥|橋|天橋|幹線)$", x)])
    b.add("高速公路（Wikidata）", [x for w in wd("t_expressway") + [x for x in wd("g_street_cn") if "高速" in x] for x in expressway_variants(w, False)])
    mw = [n for n, _ in osm("road_motorway")] + [t for n, _ in osm("route_road") if n for t in re.split(r"[\s:：;；]+", n) if re.search(r"高速|快速|国道|省道|環|环|線|线", t)]
    b.add("高速公路 / 快速路 / 国省道线（OSM）", [x for w in strict(mw) if not re.search(r"(出口|入口|匝道|辅道)$", w) for x in expressway_variants(w, False)])
    refs = [r for l in read_lines(os.path.join(RAW, "osm_names", "road_ref.tsv")) for r in l.split("\t")[0].split(";")]
    b.add("高速 / 国道 / 省道编号（OSM ref）", sorted({r.strip() for r in refs if re.fullmatch(r"[GSXYZ]\d{1,4}|[GS]\d{1,2}W|國道\d+號|台\d+線|省道\d+", r.strip())}), allow_latin=True)
    b.add("快速路 / 一级公路 / 国道（OSM trunk）", [n for n in strict([n for n, _ in osm("road_trunk")]) if not re.search(r"(出口|入口|匝道)$", n)])
    b.write()

    # 收费站 / 服务区
    t = Book(os.path.join(OUT, "03_道路交通", "03-2_收费站_服务区_停车区.md"), "高速收费站 / 服务区 / 停车区 / 休息站",
             "来源：OpenStreetMap（barrier=toll_booth、highway=services / rest_area）+ Wikidata + 人工整理。"
             "OSM 中只写地名的收费站（如“苇沟”）已自动补成“苇沟收费站”；服务区同理补“服务区 / 停车区”。", seen)
    for k, v in cur.items():
        if "收费" in k or "服务区" in k:
            t.add(k, v, allow_latin=True)
    tolls = []
    for n in strict([n for n, _ in osm("toll")]):
        n = T2S.convert(n)
        if not n or re.search(r"[门口]$|^(收费站|收费亭|出口|入口|停车场)$|停车场|小区|学校|医院|大厦|公园|景区", n):
            continue
        tolls.append(n if re.search(r"收费(站|所|广场|处)", n) else n + "收费站")
    t.add("高速收费站（OSM）", tolls)
    svc = []
    for n, e in [(n, e) for n, e in osm("services") if n and not NOISY.search(n)]:
        n = T2S.convert(n)
        if not n or n in ("服务区", "停车区", "休息区", "休息亭", "避风港", "停车场", "休息站") or re.search(r"(加油站|充电站|便利店|厕所|停车场)$", n):
            continue
        if not re.search(r"(服务区|停车区|休息区|服务站|休息站|驿站|服务中心)$", n):
            n = n + ("服务区" if e == "services" else "停车区")
        svc.append(n)
    t.add("高速服务区 / 停车区（OSM）", svc)
    t.add("服务区（Wikidata）", wd("t_rest_area"))
    t.write()

    # 城市道路（主干）+ 支路
    road_hutong = re.compile(r"(胡同|斜街|夹道|弄|弄堂|里弄|巷)$")
    rstop = re.compile(r"^(辅路|主路|匝道|出口|入口|内部道路|小区道路|无名路|人行道|步行街|广场|停车场|环岛|引道|便道|村道|乡道|县道|机耕路|田间道路|消防通道|施工便道)$|出口$|入口$|匝道$|[A-Za-z]\d{2,}")
    for fn, title, kinds, minc in [("03-3_城市道路_主干道_次干道.md", "城市道路 · 主干道 / 次干道 / 大道（全国含港澳台）", ["road_major"], 1),
                                    ("03-4_城市道路_支路_街巷.md", "城市道路 · 支路 / 街巷 / 小路（全国含港澳台）", ["road_minor"], 1)]:
        rb = Book(os.path.join(OUT, "03_道路交通", fn), title,
                  "来源：OpenStreetMap 中国及台湾数据（2026-10-21 快照）highway=* 路名，繁转简、去重，并剔除匝道/出入口/门牌类名称。按道路通名分小节。", seen)
        names = [re.sub(r"(?<=[路街道])[一二三四五六七八九十东西南北中首]{1,2}段$", "", n) for n in strict([n for k in kinds for n, _ in osm(k, minc)]) if not rstop.search(n)]
        if "minor" in fn:
            names = [n for n in names if not road_hutong.search(T2S.convert(n)) and not re.search(r"\d+号|\d+[弄巷]", n)]
        buckets = collections.OrderedDict([("大道 / 大街", r"(大道|大街)$"), ("路", r"路$"), ("街", r"街$"), ("道（港澳台常见）", r"道$"),
                                           ("桥 / 隧道 / 立交", r"(桥|隧道|立交|互通|高架|天桥)$"), ("线 / 公路", r"(线|公路)$"),
                                           ("坊 / 里 / 巷 / 弄 / 胡同", r"(坊|里|巷|弄|胡同|夹道)$"), ("广场 / 环岛 / 其他地名", r"(广场|环岛|转盘|环|圈|口|坡|岭|湾|堤|坝|塘|营|屯|庄|园|苑|城|港|岗|桥头)$")])
        tmp = collections.defaultdict(list)
        for n in names:
            s = T2S.convert(n)
            for sec, r in buckets.items():
                if re.search(r, s):
                    tmp[sec].append(n)
                    break
        for sec in buckets:
            rb.add(sec, tmp[sec])
        if "major" in fn:
            rb.add("街道（Wikidata）", [x for x in wd("g_street_cn") if "高速" not in x])
            rb.add("桥梁 / 隧道（Wikidata）", wd("t_bridge_tunnel"))
        rb.write()


# ---------------- 铁路 ----------------

def build_rail():
    b = Book(os.path.join(OUT, "04_铁路_高铁_地铁.md"), "铁路 / 高铁线路 / 火车站 / 地铁（含港澳台）",
             "来源：12306 官方车站名表（station_name.js，自动补“××站”）、中文维基《中华人民共和国高铁线路列表》《“四纵四横”铁路快速客运通道》《港鐵車站列表》《臺灣鐵路車站列表》《澳门轻轨》、"
             "Wikidata（中国境内高铁线、铁路线、车站、地铁线路与车站）、OpenStreetMap（railway=station、route=train/subway 关系）、人工整理（八纵八横通道、车型、席别等）。", set())
    cur = curated("04_rail.txt")
    for k, v in cur.items():
        b.add(k, v, allow_latin=True)
    hsr = [x for x in wiki_links(wiki("中华人民共和国高铁线路列表")) + wiki_links(wiki("“四纵四横”铁路快速客运通道"))
           if re.search(r"(铁路|鐵路|客运专线|客運專線|城际|城際|高铁|高鐵|通道|快速铁路)$", x)]
    b.add("高铁 / 城际 / 客专线路（维基 + Wikidata）", hsr + wd("t_hsr_line"))
    b.add("普速 / 地方铁路线路（Wikidata + 维基）", [x for x in wd("t_rail_line") + wiki_links(wiki("中国铁路线路列表")) if re.search(r"(铁路|鐵路|线|線|支线)$", x) and not re.search(r"地铁|地鐵|轨道交通|捷运|捷運", x)])
    js = open(os.path.join(RAW, "station_name.js"), encoding="utf-8").read()
    st = [p.split("|")[1] for p in js.split("@")[1:] if len(p.split("|")) > 2]
    b.add("12306 全国铁路客运站", [y for s in st for y in (s, s + "站")])
    b.add("火车站 / 高铁站（Wikidata + OSM）", [x for x in wd("t_station") if not re.search(r"(地铁|捷运|捷運|輕軌|轻轨)", x)] + strict([n for n, e in osm("rail_station") if e not in ("subway", "light_rail")]))
    b.add("中国香港港铁车站（维基百科）", [x for x in wiki_links(wiki("港鐵車站列表")) if re.search(r"站$", x)] + [x for x in wiki_links(wiki("港鐵車站列表")) if re.search(r"站$", x)], keep_trad=False)
    b.add("中国台湾台铁 / 高铁 / 捷运车站（维基百科）", strict([x for x in wiki_links(wiki("臺灣鐵路車站列表")) if re.search(r"(站|車站)$", x) and not re.search(r"號誌|號志|停靠|航空|發電", x)]))
    b.add("中国澳门轻轨车站（维基百科）", [x for x in wiki_links(wiki("澳门轻轨")) if re.search(r"站$", x)])
    b.add("地铁 / 轻轨 / 有轨电车线路（Wikidata + OSM）", wd("t_metro_line") + [t for k in ("route_subway", "route_light_rail", "route_tram") for n, _ in osm(k) if n for t in [re.split(r"[:：]", n)[0].strip()] if re.search(r"[\u4e00-\u9fff]{2,}.*(线|線)$", t) and " " not in t])
    b.add("地铁 / 轻轨车站（Wikidata + OSM）", wd("t_metro_station") + strict([n for n, e in osm("pt_station")]) + strict([n for n, e in osm("rail_station") if e in ("subway", "light_rail")]))
    b.add("铁路线路关系（OSM route）", strict([re.split(r"[:：]", n)[0].strip() for k in ("route_train", "route_railway") for n, _ in osm(k) if n]))
    b.write()


# ---------------- 品牌 ----------------

def build_brands():
    b = Book(os.path.join(OUT, "05_品牌_企业.md"), "品牌 / 企业（各行各业，中外）",
             "来源：人工按行业整理的常用品牌（中英文名并列）+ Wikidata（品牌、商标、食品/化妆品/服装品牌、中国含港澳台企业、各类公司：航空/银行/零售/连锁餐饮/酒店/软件/游戏开发商等）+ OpenStreetMap（门店 brand 标签）。", set())
    for k, v in curated("05_brands.txt").items():
        b.add(k, v, allow_latin=True)
    b.add("门店连锁品牌（OSM brand 标签）", [n for n, _ in osm("brand")] + [n for n, _ in osm("brand_en", 3)], allow_latin=True)
    b.add("品牌 / 商标（Wikidata）", wd("brand") + wd("brand_en"), allow_latin=True)
    b.add("中国企业（含港澳台，Wikidata）", wd("company_cn"))
    b.add("航空 / 银行 / 零售 / 餐饮 / 酒店 / 软件 / 游戏公司（Wikidata）", wd("company_type"))
    b.add("全球企业（Wikidata）", wd("company"))
    b.write()


# ---------------- 人物 ----------------

def build_people():
    seen = set()
    cur = curated("06_people.txt")
    groups = [("06-1_华语明星_名人_网红.md", "华语明星 / 名人 / 网红主播（人工整理 + Wikidata 中国含港澳台人物）",
               "来源：人工整理高频华语歌手、演员、企业家、学者、作家、网红主播、UP主；Wikidata 国籍为中国（含港澳台）且有 3 个以上维基语言版本的人物。",
               [("__cur__", None), ("中国（含港澳台）知名人物（Wikidata）", ["p_cn_people"]), ("历史名人（THUOCL）", "thu_lishimingren")]),
              ("06-2_歌手_音乐人_乐队.md", "歌手 / 音乐人 / 乐队组合（全球）", "来源：Wikidata 职业为 歌手、音乐家、作曲家、词曲作者、说唱歌手、唱作人、唱片制作人、DJ 的人物，以及乐队/男团/女团等音乐团体（中文标签，繁转简去重）。",
               [("歌手（Wikidata）", ["p_singer_Q177220", "p_singer_Q488205", "p_singer_Q2252262"]), ("音乐人 / 作曲 / 制作人 / DJ（Wikidata）", ["p_singer_Q639669", "p_singer_Q36834", "p_singer_Q753110", "p_singer_Q183945", "p_singer_Q130857"]), ("乐队 / 男团 / 女团 / 组合（Wikidata）", ["group_music"])]),
              ("06-3_演员_导演_主持人.md", "演员 / 导演 / 编剧 / 主持人 / 模特 / 声优 / 喜剧演员（全球）", "来源：Wikidata 对应职业人物中文标签。",
               [("演员（Wikidata）", ["p_actor_Q33999", "p_actor_Q10800557", "p_actor_Q10798782", "p_actor_Q2259451"]), ("声优 / 配音演员（Wikidata）", ["p_actor_Q2405480"]), ("导演 / 编剧（Wikidata）", ["p_actor_Q2526255", "p_actor_Q28389"]),
                ("主持人 / 喜剧演员 / 模特（Wikidata）", ["p_actor_Q947873", "p_actor_Q245068", "p_actor_Q4610556"]), ("偶像（Wikidata）", ["p_net_Q226008"])]),
              ("06-4_作家_作者_诗人_漫画家.md", "作家 / 作者 / 小说家 / 诗人 / 漫画家 / 剧作家 / 记者（全球）", "来源：Wikidata 对应职业人物中文标签。",
               [("作家 / 小说家 / 作者（Wikidata）", ["p_writer_Q36180", "p_writer_Q6625963", "p_writer_Q482980"]), ("诗人（Wikidata）", ["p_writer_Q49757"]), ("漫画家（Wikidata）", ["p_writer_Q191633"]), ("剧作家（Wikidata）", ["p_writer_Q214917"]), ("记者（Wikidata）", ["p_writer_Q1930187"])]),
              ("06-5_网红_YouTuber_主播_运动员_其他名人.md", "网红 / YouTuber / 主播 / 运动员 / 企业家 / 科学家 / 艺术家（全球）", "来源：Wikidata（YouTuber、网红、vlogger、Twitch 主播、Coser、运动员、企业家、科学家、哲学家、画家等）+ 全球知名人物（40 个以上维基语言版本）。",
               [("YouTuber / 网红 / 主播 / Coser（Wikidata）", ["p_net_Q17125263", "p_net_Q2906862", "p_net_Q4110598", "p_net_Q50279140", "p_net_Q18810049", "p_net_Q114890292"]),
                ("全球知名人物（Wikidata）", ["p_famous_world"]), ("企业家 / 商人（Wikidata）", ["p_other_Q131524", "p_other_Q43845"]), ("科学家 / 哲学家（Wikidata）", ["p_other_Q901", "p_other_Q4964182"]), ("画家（Wikidata）", ["p_other_Q1028181"]),
                ("运动员（足球 / 篮球 / 网球等，Wikidata）", ["p_other_Q2066131", "p_other_Q937857", "p_other_Q3665646", "p_other_Q10833314"])])]
    for fn, title, intro, secs in groups:
        b = Book(os.path.join(OUT, "06_人物", fn), title, intro, seen)
        for sec, src in secs:
            if sec == "__cur__":
                for k, v in cur.items():
                    b.add(k, v, allow_latin=True)
            elif isinstance(src, str):
                b.add(sec, [l.split("\t")[0] for l in read_lines(os.path.join(RAW, src + ".txt"))])
            else:
                b.add(sec, [x for s in src for x in wd(s)], allow_latin=sec.startswith(("乐队", "歌手", "YouTuber")))
        b.write()


# ---------------- 互联网 / 作品 ----------------

def build_internet():
    seen = set()
    cur = curated("07_internet.txt")
    b = Book(os.path.join(OUT, "07_互联网", "07-1_App_网站_产品_AI_公司_名词.md"), "互联网 · App / 网站 / 软件 / 电子产品 / AI / 公司 / 常用名词",
             "来源：人工整理（社交、视频、音乐、电商、出行、办公、开发、AI 大模型与智能体产品、游戏、互联网黑话等，含 2025–2026 新产品）+ Wikidata（网站、社交网络、移动应用、软件、操作系统、浏览器、搜索引擎、大语言模型、聊天机器人、手机/电脑/游戏机型号）+ THUOCL IT 词库。", seen)
    for k, v in cur.items():
        if k.startswith(("影视", "音乐 /", "动漫", "游戏")):
            continue
        b.add(k, v, allow_latin=True)
    b.add("网站 / App / 软件 / 操作系统（Wikidata）", wd("web") + wd("software") + wd("ai") + wd("web_en"), allow_latin=True)
    b.add("电子产品 / 手机 / 游戏机型号（Wikidata）", wd("device"), allow_latin=True)
    b.add("IT 技术名词（THUOCL）", [l.split("\t")[0] for l in read_lines(os.path.join(RAW, "thu_IT.txt"))])
    b.write()

    f = Book(os.path.join(OUT, "07_互联网", "07-2_影视_综艺_动画作品.md"), "影视作品 · 电影 / 电视剧 / 综艺 / 动画 / 纪录片（全球）",
             "来源：人工整理（含 2025–2026 热映热播：《哪吒之魔童闹海》《浪浪山小妖怪》《飞驰人生3》《功夫女足》《给阿嬷的情书》《八仙！》《欢迎来龙餐馆》《蜘蛛侠：崭新之日》《主角》《逐玉》等）+ Wikidata（电影、动画电影、电视剧、网络剧、动画剧集、电视节目中文名）。", seen)
    for k, v in cur.items():
        if k.startswith(("影视", "动漫")):
            f.add(k, v, allow_latin=True)
    f.add("电影（Wikidata）", wd("film"))
    f.add("动画电影（Wikidata）", wd("film_anim"))
    f.add("电视剧 / 网络剧 / 动画剧集 / 电视节目（Wikidata）", wd("tv"))
    f.write()

    m = Book(os.path.join(OUT, "07_互联网", "07-3_音乐_歌曲_专辑.md"), "音乐作品 · 歌曲 / 单曲 / 专辑（全球）",
             "来源：人工整理（华语经典与 2025–2026 网络热歌、欧美/日韩热门单曲）+ Wikidata（歌曲、单曲、专辑、录音室专辑中文名）。", seen)
    for k, v in cur.items():
        if k.startswith("音乐 /"):
            m.add(k, v, allow_latin=True)
    m.add("歌曲 / 单曲（Wikidata）", wd("song"), allow_latin=True)
    m.add("专辑（Wikidata）", wd("album"), allow_latin=True)
    m.write()

    g = Book(os.path.join(OUT, "07_互联网", "07-4_游戏_电竞.md"), "游戏 / 电竞（全球）", "来源：人工整理（手游、端游、主机游戏、电竞战队与术语）+ Wikidata（电子游戏中文名）。", seen)
    for k, v in cur.items():
        if k.startswith("游戏"):
            g.add(k, v, allow_latin=True)
    g.add("电子游戏（Wikidata）", wd("game"), allow_latin=True)
    g.write()

    bk = Book(os.path.join(OUT, "07_互联网", "07-5_书籍_小说_漫画.md"), "书籍 / 小说 / 漫画 / 文学作品（全球）", "来源：Wikidata（小说、文学作品、漫画系列中文名）。", seen)
    bk.add("小说 / 文学作品 / 漫画（Wikidata）", wd("book"))
    bk.write()

    moe = Book(os.path.join(OUT, "07_互联网", "07-6_萌娘百科_ACG_小众词条.md"), "ACG / 二次元 / 虚拟主播 / 网络小众词条（萌娘百科条目名）",
               "来源：萌娘百科全部条目标题（outloudvi/mw2fcitx 2026-09-11 导出）。涵盖动画、漫画、游戏角色、VOCALOID 曲目、虚拟主播、UP主、网络梗等大量小众词。已过滤含日文假名、韩文的标题与子页面，繁转简。", seen)
    ttl = [t for t in read_lines(os.path.join(RAW, "moegirl_titles.txt")) if "/" not in t and ":" not in t]
    moe.add("萌娘百科条目", ttl)
    moe.write()


# ---------------- 汽车 ----------------

def build_auto():
    b = Book(os.path.join(OUT, "08_汽车_摩托_自行车.md"), "汽车 / 摩托车 / 电动车 / 自行车（集团、品牌、子品牌、车型、功能配置、行业热词）",
             "来源：人工整理（国内外汽车集团 → 品牌 → 子品牌、在售与经典车型、2025–2026 新车如 问界M6 / 尚界Z7 / 小米YU7 / 理想L9 Livis / 比亚迪大唐 等、智驾/座舱/三电/底盘配置名词、摩托与自行车品牌车型）+ Wikidata（汽车制造商、汽车品牌、摩托车/自行车制造商、车型中英文名）+ THUOCL 汽车词库。", set())
    for k, v in curated("08_auto.txt").items():
        b.add(k, v, allow_latin=True)
    b.add("汽车 / 摩托 / 自行车制造商与品牌（Wikidata）", wd("car_maker") + wd("car_brand_all"), allow_latin=True)
    b.add("车型（Wikidata 中文名）", wd("car_model") + wd("car_model_all"))
    b.add("车型（Wikidata 英文名）", wd("car_model_en"), allow_latin=True)
    b.add("摩托车型（Wikidata）", wd("moto_model"), allow_latin=True)
    b.add("汽车名词（THUOCL）", [l.split("\t")[0] for l in read_lines(os.path.join(RAW, "thu_car.txt"))])
    b.write()


# ---------------- 热梗 ----------------

def build_memes():
    b = Book(os.path.join(OUT, "09_网络热梗_流行语.md"), "网络热梗 / 流行语（2026 最新 + 过去一年 + 常用经典）",
             "来源：公开报道检索整理（2026-10-22 检索）：《咬文嚼字》2025 年十大流行语、澎湃新闻/新周刊《2025 年度爆梗》、数英网《2026 上半年网络热词 TOP30》、京东消费及产业发展研究院 2026 上半年百大热梗、中新网/百度百科（2026 年 10 月“不烧心”）等；"
             "叠加中文维基《中国大陆网络用语列表》粗体词条与 fcitx5-pinyin-zhwiki web-slang 词库（2026-10-18）。“××”为句式占位，导入时可按需删除。", set(), sort=False)
    for k, v in curated("09_memes.txt").items():
        b.add(k, v, allow_latin=True, maxlen=24)
    slang = []
    for l in read_lines(os.path.join(RAW, "web-slang.dict.yaml")):
        if "\t" in l:
            slang.append(l.split("\t")[0])
    b.add("网络用语（fcitx5-pinyin-zhwiki web-slang）", slang, allow_latin=True, sort=True)
    txt = wiki("中国大陆网络用语列表") or open(os.path.join(RAW, "web-slang.wikitext"), encoding="utf-8").read()
    bold = re.findall(r"^\*+\s*'''(.+?)'''", txt, re.M)
    words = []
    for x in bold:
        for y in re.split(r"[、/／,，;；]|或|和", strip_wiki(x)):
            words.append(y.strip("「」“”\"' "))
    b.add("中国大陆网络用语（维基百科词条）", words, allow_latin=True, maxlen=20, sort=True)
    b.write()


def write_readme_and_all():
    # 汇总 txt
    allw = []
    seen = set()
    for p in sorted(glob.glob(os.path.join(OUT, "**", "*.md"), recursive=True)):
        if p.endswith("README.md"):
            continue
        inblock = False
        for l in open(p, encoding="utf-8"):
            l = l.rstrip("\n")
            if l.startswith("```"):
                inblock = not inblock
                continue
            if inblock and l and l not in seen:
                seen.add(l)
                allw.append(l)
    open(os.path.join(OUT, "全部词条_去重汇总.txt"), "w", encoding="utf-8").write("\n".join(allw))
    json.dump({"files": STATS, "unique_total": len(allw)}, open(os.path.join(ROOT, "raw", "stats.json"), "w"), ensure_ascii=False, indent=1)
    print("ALL unique", len(allw))


if __name__ == "__main__":
    import sys
    steps = sys.argv[1:] or ["places", "scenic", "roads", "rail", "brands", "people", "internet", "auto", "memes", "all"]
    for s in steps:
        if s == "all":
            write_readme_and_all()
        else:
            globals()["build_" + s]()
