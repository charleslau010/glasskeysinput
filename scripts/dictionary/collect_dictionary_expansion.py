from pathlib import Path
import hashlib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'research/dictionary-expansion-20261018'
SOURCES = {
    'wanxiang': ('amzxyz/rime_wanxiang', 'ed55bd5c7f94dd06d333db0c51a7dbfe50cc9bd2',
                 ['LICENSE', 'dicts/diming.dict.yaml', 'dicts/jichu.dict.yaml', 'dicts/mixed.dict.yaml']),
    'ice': ('iDvel/rime-ice', 'da1fbe602e38f26db846fa10120ee64c2b0324c0',
            ['LICENSE', 'en_dicts/en.dict.yaml', 'en_dicts/en_ext.dict.yaml']),
    'symspell': ('wolfgarbe/SymSpell', 'c239062ae02961df18ab7da1671d01b4388204e0',
                ['LICENSE', 'SymSpell/frequency_dictionary_en_82_765.txt']),
}


def plain(value):
    # 查询编码去声调，展示文本保持原样，ü 使用引擎现有的 v 编码。
    value = unicodedata.normalize('NFD', value.replace('ü', 'v')).replace('u\u0308', 'v')
    return ''.join(c for c in value if not unicodedata.combining(c)).replace(' ', '').replace("'", '').lower()


def rows(path):
    # 只解析正文的制表符词条，跳过 YAML 元数据和注释。
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        fields = line.split('\t')
        if len(fields) >= 2 and not line.startswith('#'):
            yield fields[0], fields[1], int(fields[2]) if len(fields) > 2 and fields[2].isdigit() else 10


def collect():
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, (repo, commit, files) in SOURCES.items():
        for filename in files:
            target = DEST / name / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f'https://raw.githubusercontent.com/{repo}/{commit}/{filename}'
            temporary = target.with_name(target.name + '.partial')
            try:
                with urllib.request.urlopen(url, timeout=120) as response:
                    if urllib.parse.urlparse(response.url).scheme != 'https':
                        raise ValueError('Dictionary download must remain HTTPS')
                    content = response.read(64 * 1024 * 1024 + 1)
                if not content or len(content) > 64 * 1024 * 1024:
                    raise ValueError('Dictionary download is empty or exceeds 64 MiB')
                content.decode('utf-8-sig')
                temporary.write_bytes(content)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            manifest.append({'url': url, 'file': str(target.relative_to(DEST)),
                             'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    excluded = re.compile('政府|省委|市委|县委|区委|党委|共产党|国民党|政协|人大|政治|主席|总统|总理|选举|战争|军事|色情|性爱|成人视频')
    categories = {
        'scenic': re.compile('(景区|景点|风景区|风景名胜区|国家公园|森林公园|湿地公园|地质公园|旅游区|古镇|古城|博物馆|纪念馆|度假区|游乐园|主题公园|植物园|动物园|瀑布|峡谷|山庄|海滩|沙滩)$'),
        'roads': re.compile('(胡同|弄堂|公路|高速|高速公路|快速路|大道|大街|收费站|服务区|停车区|立交桥|隧道|路|街|巷|弄)$'),
        'rail': re.compile('(高铁|铁路|城际|城际铁路|客运专线|火车站|高铁站|动车站|铁路站)$'),
        'products': re.compile('(手机|汽车|自行车|摩托车|电动车|山地车|公路车|平板|电脑|耳机|音箱|浏览器|输入法|操作系统|数据库|搜索引擎|大模型|智能体|游戏|电视剧|电影|有限公司|股份有限公司)$'),
    }
    chinese = {}
    counts = Counter()
    for text, code, weight in rows(DEST / 'wanxiang/dicts/diming.dict.yaml'):
        spelling = plain(code)
        if re.fullmatch('[a-z]+', spelling) and not excluded.search(text):
            chinese[(spelling, text)] = min(500, max(10, weight))
            counts['geography'] += 1
    for text, code, weight in rows(DEST / 'wanxiang/dicts/jichu.dict.yaml'):
        spelling = plain(code)
        if not re.fullmatch('[a-z]+', spelling) or excluded.search(text):
            continue
        for category, pattern in categories.items():
            if len(text) >= 3 and pattern.search(text):
                chinese[(spelling, text)] = min(500, max(10, weight))
                counts[category] += 1
                break
    # 混合产品仅取来源明确的品牌型号，不把任意代码转换成不存在的型号。
    mixed_brands = re.compile('^(小米|问界|理想|蔚来|极氪|比亚迪|腾势|方程豹|华为|荣耀|红米|苹果|iPhone|iPad|MacBook|ChatGPT|DeepSeek|Claude|Gemini)')
    for text, code, weight in rows(DEST / 'wanxiang/dicts/mixed.dict.yaml'):
        if not mixed_brands.search(text) or excluded.search(text):
            continue
        # 混合编码中的数字不能由拼音键输入；只使用上游已给出的纯字母编码。
        spelling = plain(code)
        if re.fullmatch('[a-z]+', spelling):
            chinese[(spelling, text)] = 100
            counts['mixed_products'] += 1
    english = {}
    for line in (DEST / 'symspell/SymSpell/frequency_dictionary_en_82_765.txt').read_text(encoding='utf-8-sig').splitlines():
        fields = line.split()
        if len(fields) == 2 and re.fullmatch('[a-z]{2,32}', fields[0]) and fields[1].isdigit():
            english[fields[0]] = [fields[0], max(1, min(2000000000, int(fields[1]) // 1000))]
    for filename in ['en.dict.yaml', 'en_ext.dict.yaml']:
        for text, code, weight in rows(DEST / 'ice/en_dicts' / filename):
            key = code.lower()
            if re.fullmatch('[a-z]{2,32}', key) and re.fullmatch('[a-zA-Z]{2,32}', text):
                frequency = english.get(key, [text, 100])[1]
                english[key] = [text, frequency]
    (DEST / 'supplemental-pinyin.tsv').write_text(''.join(f'{code}\t{text}\t{weight}\n' for (code, text), weight in sorted(chinese.items())), encoding='utf-8')
    (DEST / 'supplemental-english.tsv').write_text(''.join(f'{text}\t{weight}\n' for key, (text, weight) in sorted(english.items())), encoding='utf-8')
    report = {'retrieved': '2026-10-18', 'sources': manifest, 'selected_categories': dict(counts),
              'pinyin_entries': len(chinese), 'english_entries': len(english),
              'coverage': 'Source-derived subset, not exhaustive or individually current-verified. No general notable-person import. Road and scenic suffix selection is heuristic.'}
    (DEST / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'sources'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        collect()
    except (OSError, ValueError) as error:
        raise SystemExit(f'公开词库采集失败：{error}') from error
