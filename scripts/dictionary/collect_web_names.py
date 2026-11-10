import concurrent.futures
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/web-names-20261018'
sys.path.insert(0, str(OUT / 'python-deps'))
from opencc import OpenCC
from pypinyin import Style, lazy_pinyin

CONVERTER = OpenCC('t2s')
RECORDS = {}
SOURCES = []
BLOCK = re.compile('政府|省委|市委|县委|区委|党委|共产党|国民党|政协|人大|政治|主席|总统|总理|选举|战争|军事|色情|性爱|成人视频|纪念馆|国父|革命|孙中山|毛泽东|习近平|蒋介石|蒋经国|邓小平|周恩来|普京|特朗普|拜登')


def fetch(name, url, encoding=None):
    # 每次采集保留实际响应和校验值；失败不使用搜索摘要冒充完整名单。
    target = OUT / (name + '.raw')
    try:
        if not target.exists():
            response = requests.get(url, timeout=45)
            response.raise_for_status()
            target.write_bytes(response.content)
        content = target.read_bytes()
        SOURCES.append({'name': name, 'url': url, 'retrieved': '2026-10-18',
                        'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)})
        return BeautifulSoup(content.decode(encoding) if encoding else content, 'html.parser')
    except (requests.RequestException, UnicodeError, OSError) as error:
        SOURCES.append({'name': name, 'url': url, 'error': str(error)})
        return None


def add(name, category, source, detail=None):
    text = CONVERTER.convert(re.sub(r'\s+', ' ', name).strip())
    if not 2 <= len(text) <= 32 or BLOCK.search(text) or re.search('委员会|管委会|办事处|办事|再开乡', text):
        return
    if not re.fullmatch(r'[\u3400-\u9fffA-Za-z0-9· .+\-]+', text):
        return
    if not re.search('[\u3400-\u9fffA-Za-z]', text):
        return
    record = RECORDS.setdefault((category, text), {'name': text, 'original': name,
                                                  'category': category, 'sources': []})
    ref = {'source': source}
    if detail:
        ref['detail'] = detail
    if ref not in record['sources']:
        record['sources'].append(ref)


def collect():
    OUT.mkdir(parents=True, exist_ok=True)
    admin_url = 'https://raw.githubusercontent.com/modood/Administrative-divisions-of-China/master/dist/pcas-code.json'
    fetch('admin', admin_url)
    if (OUT / 'admin.raw').exists():
        def walk(items):
            for item in items:
                if item['name'] not in ('市辖区', '县', '省直辖县级行政区划', '自治区直辖县级行政区划'):
                    add(item['name'], 'places', 'admin', item['code'])
                walk(item.get('children', []))
        walk(json.loads((OUT / 'admin.raw').read_bytes()))
    taiwan = fetch('taiwan', 'https://jatraveling.tw/blog/post/51295')
    if taiwan:
        for name in re.findall(r'\b\d{3}\s*([\u3400-\u9fff]{2,8}[鄉鎮市區])', taiwan.get_text(' ', strip=True)):
            add(name, 'places_taiwan', 'taiwan')
    # 目录是真实名称列表，而不是按名称后缀从旧词库捞词。
    book = fetch('hutongs2', 'https://www.newton.com.tw/wiki/北京地名典（修訂版）')
    if book:
        lines = book.get_text('\n', strip=True).splitlines()
        start = next((i for i, line in enumerate(lines) if line == '東城區'), len(lines))
        for line in lines[start:]:
            if re.fullmatch('[\u3400-\u9fff]{2,24}', line) and re.search('胡同|巷|街|路|里|村|條$', line) and '办事' not in CONVERTER.convert(line):
                add(line, 'roads', 'hutongs2')
    stations = fetch('stations', 'https://kyfw.12306.cn/otn/resources/js/framework/station_name.js', 'utf-8')
    if stations:
        for entry in (OUT / 'stations.raw').read_text().split('@')[1:]:
            fields = entry.split('|')
            if len(fields) > 4 and re.fullmatch('[\u3400-\u9fff]{2,20}', fields[1]):
                add(fields[1], 'rail_stations', 'stations', fields[2])
                add(fields[1] + '站', 'rail_stations', 'stations', fields[2])
    scenic = fetch('scenic', 'https://www.sh-cits.cn/scene/area_64.htm')
    if scenic:
        for anchor in scenic.select('a[href]'):
            if re.fullmatch(r'/scene/scene_\d+\.htm', anchor['href']):
                for name in re.split('[、，]', anchor.get_text(strip=True)):
                    add(name, 'scenic', 'scenic', anchor['href'])
        areas = {a['href'] for a in scenic.select('a[href]') if re.fullmatch(r'/scene/area_\d+\.htm', a['href'])}
        for index, path in enumerate(sorted(areas)):
            page = fetch(f'scenic_area_{index}', 'https://www.sh-cits.cn' + path)
            if page:
                for anchor in page.select('a[href]'):
                    if re.fullmatch(r'/scene/scene_\d+\.htm', anchor['href']):
                        for name in re.split('[、，]', anchor.get_text(strip=True)):
                            add(name, 'scenic', f'scenic_area_{index}', anchor['href'])
    brands = fetch('brands', 'https://shopex.cn/news/30542')
    if brands:
        for row in brands.select('table tr'):
            cells = row.select('td')
            if len(cells) >= 2:
                for name in re.split('[、，]', cells[-1].get_text(strip=True)):
                    add(name, 'brands', 'brands')
    ai = fetch('ai', 'https://ai-bot.cn/')
    if ai:
        for card in ai.select('a.card'):
            title = card.select_one('strong')
            if title:
                # 单独的英文写法和中文写法来自同一标题，不提取广告描述。
                full = title.get_text(strip=True)
                add(full, 'internet_products', 'ai', card.get('href'))
                for name in re.split('[（(）)]', full):
                    add(name, 'internet_products', 'ai', card.get('href'))
    reference = fetch('writers', 'https://fbrowser.org/wikipedia/wiki/Wikipedia:VA')
    allowed = {'藝術家、建築師': 'people', '作家、劇作家、詩人': 'people',
               '作曲家、音樂家': 'people', '電影導演、編劇、藝人': 'people',
               '發明家、科學家、數學家': 'people', '電腦、互聯網': 'internet_terms',
               '電影、電台、電視': 'film_tv', '音樂': 'music'}
    if reference:
        for heading in reference.select('h3,h4'):
            category = allowed.get(heading.get_text(strip=True))
            if not category:
                continue
            for element in heading.next_elements:
                if element is not heading and getattr(element, 'name', None) in ('h2', 'h3', 'h4'):
                    break
                if getattr(element, 'name', None) != 'a':
                    continue
                if element.get('href', '').startswith('/wikipedia/wiki/') and not element['href'].startswith('/wikipedia/wiki/File:'):
                    title = element.get('title', element.get_text(strip=True))
                    if not title.startswith(('Wikipedia:', '分類:', 'File:', 'Category:')):
                        add(re.sub(r'\s*[（(][^()（）]*[)）]$', '', title), category, 'writers', element['href'])
    cars = fetch('cars2', 'https://car.autohome.com.cn/')
    if cars:
        for anchor in cars.select('a[href]'):
            if anchor.get('name') == 'a_brand' or re.search(r'/price/(?:series|brand)-\d+', anchor['href']):
                add(anchor.get_text(strip=True), 'cars', 'cars2', anchor['href'])
    if cars:
        brand_ids = set()
        for anchor in cars.select('a[name=a_brand]'):
            href = anchor.get('href', '')
            if not href.startswith('/price/list-'):
                continue
            try:
                brand_ids.add(int(href.split('/price/list-', 1)[1].split('-')[8]))
            except (IndexError, ValueError):
                continue
        brand_ids = sorted(brand_ids)
        def download_brand(brand_id):
            return brand_id, fetch(f'car_brand_{brand_id}', f'https://car.autohome.com.cn/price/brand-{brand_id}.html')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for brand_id, page in pool.map(download_brand, brand_ids):
                if not page:
                    continue
                for anchor in page.select('.list-dl-text a[href]'):
                    if re.search(r'/price/series-\d+', anchor['href']):
                        name = re.sub(r'\s*[（(](?:停售|停产)[)）]$', '', anchor.get_text(strip=True))
                        add(name, 'car_models', f'car_brand_{brand_id}', anchor['href'])
    films = fetch('films2', 'https://www.anyrank.net/zh/ranking/top-25-highest-rated-movies-on-douban')
    if films:
        for row in films.select('table tr'):
            cells = row.select('td')
            if len(cells) >= 4 and cells[0].get_text(strip=True).isdigit():
                add(cells[1].get_text(strip=True), 'film_titles', 'films2', '2026-10-16')
                for director in re.split(r'\s*/\s*', cells[3].get_text(strip=True)):
                    add(director, 'people', 'films2')
    songs = fetch('songs2', 'https://fbrowser.org/wikipedia/zh-hant/Template:周杰倫歌曲')
    if songs:
        for anchor in songs.select('.navbox-list a'):
            title = anchor.get('title', anchor.get_text(strip=True))
            if anchor.get('href', '').startswith('/wikipedia/') and not re.search('模板|獎項|演唱會|作品列表|維基|音樂作品|創作作品', title):
                add(re.sub(r'\s*[（(][^()（）]*[)）]$', '', title), 'song_titles', 'songs2', anchor.get('href'))
    motor = fetch('motorcycles', 'https://www.autohome.com.cn/motorbike')
    if motor:
        for anchor in motor.select('a[href]'):
            if re.search(r'/motorbike/series/\d+/?$', anchor['href']):
                name = re.split('[¥￥]', anchor.get_text(strip=True))[0]
                if '新闻' not in name:
                    add(name, 'motorcycles', 'motorcycles', anchor['href'])
    memes = OUT / 'memes-api-js.raw'
    if memes.exists():
        # 动态网页的公开构建资源含词条数据，严格只选中性标签，不执行下载的JavaScript。
        text = memes.read_text()
        for match in re.finditer(r'词条名:`([^`]+)`(.*?)(?=\},\w+=\{|$)', text, re.S):
            name, body = match.groups()
            if len(body) > 10000 or re.search('政治|色情|性心理|侵犯|辱骂|歧视|军事|示例|模板|原神牛逼', body):
                continue
            if not re.search('猫咪|职场|穿搭|幽默|音乐|搞笑|社交|2024|2025|2026|网络用语', body):
                continue
            year = re.search(r'词条年份:[`\"]?(20\d{2})', body)
            add(name, 'memes', 'https://xn--vqqq8jxym.com/assets/api.C269eUUu.js', year.group(1) if year else None)
    # 人工复核过的网页提取项仍保留URL，不把模型自身记忆当成来源。
    for filename in ('verified-page-names.json', 'expanded-page-names.json'):
        verified = OUT / filename
        if verified.exists():
            for source in json.loads(verified.read_text()):
                for name in source['names']:
                    add(name, source['category'], source['url'], source.get('detail') or source.get('published'))
    candidates = {}
    unknown = []
    for record in RECORDS.values():
        text = record['name']
        # 汉字自动拼音是初步编码，多音地名需另行校对；保留原词库已有读音。
        normalized = text.replace('·', '').replace(' ', '').replace('-', '').replace('.', '').replace('+', 'plus')
        normalized = normalized.translate(str.maketrans(dict(zip('0123456789', ['ling', 'yi', 'er', 'san', 'si', 'wu', 'liu', 'qi', 'ba', 'jiu']))))
        spelling = ''.join(lazy_pinyin(normalized, style=Style.NORMAL, errors=lambda value: [value.lower()])).replace('ü', 'v')
        if re.fullmatch('[a-z]+', spelling):
            record['pinyin'] = spelling
            candidates[(spelling, text)] = 80 if record['category'] in ('places', 'roads') else 100
        else:
            unknown.append(text)
    records = sorted(RECORDS.values(), key=lambda row: (row['category'], row['name']))
    (OUT / 'names.jsonl').write_text(''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in records), encoding='utf-8')
    (OUT / 'pinyin.tsv').write_text(''.join(f'{spelling}\t{text}\t{weight}\n' for (spelling, text), weight in sorted(candidates.items())), encoding='utf-8')
    english = {record['name'] for record in records if re.fullmatch('[A-Za-z]{2,32}', record['name'])}
    (OUT / 'english.tsv').write_text(''.join(f'{text}\t100\n' for text in sorted(english)), encoding='utf-8')
    report = {'retrieved': '2026-10-18', 'categories': dict(Counter(record['category'] for record in records)),
              'records': len(records), 'unique_pinyin_pairs': len(candidates), 'sources': SOURCES,
              'unencoded': unknown, 'limits': 'Not exhaustive. Place polyphones are machine-generated and need review. Historical sources are not evidence of current operation.'}
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'sources'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    collect()
