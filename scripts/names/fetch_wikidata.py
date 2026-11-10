"""从 Wikidata SPARQL 按类别抓取中文标签（zh / zh-cn / zh-hans / zh-hk / zh-tw）。
输出：raw/wd/<cat>.txt，每行一个标签。
"""
import os, sys, subprocess, csv, io, time

OUT = os.path.join(os.path.dirname(__file__), "..", "raw", "wd")
os.makedirs(OUT, exist_ok=True)
UA = "GlassKeys-lexicon-builder/0.1 (https://glasskeysinput.online)"


PRE = ("PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> "
       "PREFIX wikibase: <http://wikiba.se/ontology#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> ")


def wd(q, timeout=280):
    # 官方 WDQS 有 60s 超时，改用 QLever 镜像（同一份 Wikidata 数据）
    for a in range(4):
        r = subprocess.run(["curl", "-s", "-m", str(timeout), "https://qlever.dev/api/wikidata",
                            "--data-urlencode", "query=" + PRE + q, "-H", "Accept: text/csv", "-A", UA],
                           capture_output=True, text=True).stdout
        if (not r) or r.startswith("<") or "Exception" in r[:3000] or not r.startswith("l"):
            time.sleep(20 * (a + 1)); continue
        return [row["l"] for row in csv.DictReader(io.StringIO(r))]
    return None

LANGS = '("zh","zh-cn","zh-hans","zh-hk","zh-tw","zh-hant","zh-sg","zh-mo")'


def q_occ(occs, smin):
    return ("SELECT DISTINCT ?l WHERE { VALUES ?c { %s } ?x wdt:P106 ?c; wikibase:sitelinks ?s. FILTER(?s>=%d) "
            "?x wdt:P31 wd:Q5. ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % (" ".join("wd:" + o for o in occs), smin, LANGS))


def q_cls(cls, smin, extra=""):
    return ("SELECT DISTINCT ?l WHERE { VALUES ?c { %s } ?x wdt:P31 ?c; wikibase:sitelinks ?s. FILTER(?s>=%d) %s "
            "?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % (" ".join("wd:" + o for o in cls), smin, extra, LANGS))

CN = "VALUES ?ctry { wd:Q148 wd:Q865 wd:Q8646 wd:Q14773 } ?x wdt:P17 ?ctry."

JOBS = {
    # 人物（按职业逐个查，避免超时）
    **{f"p_singer_{o}": q_occ([o], 2) for o in "Q177220 Q639669 Q36834 Q753110 Q2252262 Q488205 Q183945 Q130857".split()},
    **{f"p_actor_{o}": q_occ([o], 2) for o in "Q33999 Q10800557 Q10798782 Q2405480 Q2259451 Q4610556 Q2526255 Q28389 Q947873 Q245068".split()},
    **{f"p_net_{o}": q_occ([o], 1) for o in "Q17125263 Q2906862 Q4110598 Q50279140 Q18810049 Q114890292 Q226008".split()},
    **{f"p_writer_{o}": q_occ([o], 2) for o in "Q36180 Q6625963 Q49757 Q482980 Q191633 Q214917 Q1930187".split()},
    **{f"p_other_{o}": q_occ([o], 8) for o in "Q901 Q131524 Q43845 Q4964182 Q1028181 Q2066131 Q937857 Q3665646 Q10833314".split()},
    "group_music": q_cls("Q215380 Q216337 Q641066 Q2088357 Q5741069".split(), 2),
    # 公司/品牌
    "company": q_cls("Q4830453 Q6881511 Q891723 Q783794".split(), 4),
    "company_cn": q_cls("Q4830453 Q6881511 Q891723 Q783794".split(), 1, CN),
    "company_type": q_cls("Q1058914 Q18388277 Q210167 Q46970 Q22687 Q507619 Q18043413 Q18509232 Q1631129 Q18534542".split(), 1),
    "brand": q_cls("Q431289 Q167270 Q16323605 Q55315112 Q133459332".split(), 1),
    # 互联网/产品
    "web": q_cls("Q35127 Q3220391 Q620615 Q166142 Q9135 Q6368 Q4182287 Q3390477".split(), 1),
    "ai": q_cls("Q115305900 Q870780".split(), 1),
    "software": q_cls(["Q7397"], 3),
    "device": q_cls("Q19723451 Q73343954 Q113990168 Q8076 Q22645".split(), 1),
    "film": q_cls(["Q11424"], 4),
    "film_anim": q_cls(["Q202866"], 2),
    "tv": q_cls("Q5398426 Q526877 Q63952888 Q15416".split(), 2),
    "song": q_cls("Q7366 Q134556".split(), 3),
    "album": q_cls("Q482994 Q208569".split(), 3),
    "game": q_cls(["Q7889"], 3),
    "book": q_cls("Q8261 Q7725634 Q21198342".split(), 3),
    # 汽车/摩托/自行车
    "car_maker": q_cls("Q786820 Q15081030 Q29044175 Q108460239 Q10429667 Q131361364 Q117826820".split(), 1),
    "car_model": q_cls(["Q3231690"], 1),
    "moto_model": q_cls(["Q23866334"], 1),
    # 景区（中国含港澳台）
    "scenic_cn": q_cls("Q570116 Q8502 Q23397 Q46169 Q179049 Q44539 Q5393308 Q1107656 Q22698 Q33506 Q839954 Q16560 Q12280 Q35509 Q34038 Q40080 Q23442 Q194195".split(), 1, CN),
    "scenic_heritage": "SELECT DISTINCT ?l WHERE { ?x wdt:P1435 wd:Q1188574. ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
}

if __name__ == "__main__":
    only = sys.argv[1:] or list(JOBS)
    for k in only:
        fn = os.path.join(OUT, k + ".txt")
        if os.path.exists(fn) and os.path.getsize(fn) > 0:
            print(k, "skip", flush=True); continue
        t = time.time(); res = wd(JOBS[k])
        if res is None:
            print(k, "FAIL", f"{time.time()-t:.0f}s", flush=True); continue
        open(fn, "w").write("\n".join(res))
        print(k, len(res), f"{time.time()-t:.0f}s", flush=True)
        time.sleep(2)


# ===== 追加任务（交通 / 港澳台地名 / 胡同），保留原逻辑 =====
def q_sub(cls, extra=""):
    """P31/P279* 子类 + 中国含港澳台。"""
    return ("SELECT DISTINCT ?l WHERE { ?x wdt:P31/wdt:P279* wd:%s. %s %s ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }"
            % (cls, CN, extra, LANGS))

JOBS2 = {
    "t_hsr_line": q_sub("Q858485"),
    "t_rail_line": q_sub("Q728937"),
    "t_station": q_sub("Q55488"),
    "t_metro_station": q_sub("Q928830"),
    "t_metro_line": q_sub("Q15079663"),
    "t_expressway": q_sub("Q46622"),
    "t_rest_area": q_sub("Q786014"),
    "t_bridge_tunnel": "SELECT DISTINCT ?l WHERE { VALUES ?c { wd:Q12280 wd:Q44377 } ?x wdt:P31/wdt:P279* ?c. %s ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % (CN, LANGS),
    "g_hutong": "SELECT DISTINCT ?l WHERE { ?x wdt:P31/wdt:P279* wd:Q1065367. ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
    "g_street_cn": "SELECT DISTINCT ?l WHERE { VALUES ?c { wd:Q79007 wd:Q34442 } ?x wdt:P31/wdt:P279* ?c. %s ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % (CN, LANGS),
    "g_tw_admin": "SELECT DISTINCT ?l WHERE { ?x wdt:P17 wd:Q865; wdt:P31/wdt:P279* wd:Q56061. ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
    "g_hkmo_place": "SELECT DISTINCT ?l WHERE { VALUES ?ctry { wd:Q8646 wd:Q14773 } ?x wdt:P17 ?ctry; wdt:P625 ?co. ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
    "g_tw_place": "SELECT DISTINCT ?l WHERE { ?x wdt:P17 wd:Q865; wdt:P31/wdt:P279* wd:Q486972. ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
    "g_cn_mountain_river": "SELECT DISTINCT ?l WHERE { VALUES ?c { wd:Q8502 wd:Q4022 wd:Q23397 wd:Q23442 wd:Q46831 } ?x wdt:P31/wdt:P279* ?c. %s ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % (CN, LANGS),
    "p_cn_people": "SELECT DISTINCT ?l WHERE { ?x wdt:P31 wd:Q5; wdt:P27 ?ctry; wikibase:sitelinks ?s. VALUES ?ctry { wd:Q148 wd:Q865 wd:Q8646 wd:Q14773 wd:Q13426199 } FILTER(?s>=3) ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
    "p_famous_world": "SELECT DISTINCT ?l WHERE { ?x wdt:P31 wd:Q5; wikibase:sitelinks ?s. FILTER(?s>=40) ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
    "car_brand_all": "SELECT DISTINCT ?l WHERE { VALUES ?c { wd:Q786820 wd:Q10429667 wd:Q15081030 wd:Q29044175 wd:Q131361364 wd:Q117826820 wd:Q108460239 } ?x wdt:P31/wdt:P279* ?c. ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
    "car_model_all": "SELECT DISTINCT ?l WHERE { VALUES ?c { wd:Q3231690 wd:Q23866334 } ?x wdt:P31/wdt:P279* ?c. ?x rdfs:label ?l. FILTER(LANG(?l) IN %s) }" % LANGS,
    "car_model_en": "SELECT DISTINCT ?l WHERE { ?x wdt:P31 wd:Q3231690; wikibase:sitelinks ?s. FILTER(?s>=3) ?x rdfs:label ?l. FILTER(LANG(?l)=\"en\") }",
    "brand_en": "SELECT DISTINCT ?l WHERE { VALUES ?c { wd:Q431289 wd:Q167270 } ?x wdt:P31 ?c; wikibase:sitelinks ?s. FILTER(?s>=8) ?x rdfs:label ?l. FILTER(LANG(?l)=\"en\") }",
    "web_en": "SELECT DISTINCT ?l WHERE { VALUES ?c { wd:Q35127 wd:Q3220391 wd:Q620615 wd:Q166142 wd:Q115305900 wd:Q870780 } ?x wdt:P31 ?c; wikibase:sitelinks ?s. FILTER(?s>=5) ?x rdfs:label ?l. FILTER(LANG(?l)=\"en\") }",
}

if __name__ == "__main__" and os.environ.get("JOBS2"):
    for k, q in JOBS2.items():
        fn = os.path.join(OUT, k + ".txt")
        if os.path.exists(fn) and os.path.getsize(fn) > 0:
            continue
        t = time.time(); res = wd(q)
        print(k, "FAIL" if res is None else len(res), f"{time.time()-t:.0f}s", flush=True)
        if res is not None:
            open(fn, "w").write("\n".join(res))
