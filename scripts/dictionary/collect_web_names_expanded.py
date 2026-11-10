import concurrent.futures
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/web-names-20261018'
sys.path.insert(0, str(OUT / 'python-deps'))
from opencc import OpenCC

CONVERTER = OpenCC('t2s')
NOW = datetime.now().astimezone().isoformat()
SESSION = 'expanded-' + datetime.now().strftime('%Y%m%d-%H%M%S')
ROWS = []
SOURCES = []
BLOCK = re.compile('政府|委员会|政治|战争|军事|色情|性爱|总统|主席|共产党|选举|习近平|毛泽东|普京|特朗普|拜登')


def download(url, payload=None):
    key = hashlib.sha256((url + json.dumps(payload, sort_keys=True)).encode()).hexdigest()[:16]
    target = OUT / SESSION / (key + '.raw')
    try:
        # 每次真正请求并存原始响应，防止旧缓存被当成新采集；失败不使用搜索摘要替代。
        response = requests.get(url, timeout=25) if payload is None else requests.post(url, json=payload, timeout=25)
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        evidence = {'url': url, 'retrieved': NOW, 'status': response.status_code,
                    'bytes': len(response.content), 'sha256': hashlib.sha256(response.content).hexdigest(),
                    'raw': str(target.relative_to(ROOT))}
        if payload is not None:
            evidence['request'] = payload
        if response.content.lstrip().startswith((b'{', b'[')):
            text = response.content.decode('utf-8', errors='replace')
        else:
            text = BeautifulSoup(response.content, 'html.parser').decode()
        return text, evidence
    except requests.RequestException as error:
        return None, {'url': url, 'retrieved': NOW, 'error': str(error)}


def record(url, category, names, detail=None):
    # 只允许中性名称，标题中的版本括号、剧情描述和污染文本不直接作为词条。
    clean = sorted({CONVERTER.convert(name.strip()) for name in names
                    if 2 <= len(name.strip()) <= 32 and not BLOCK.search(name)
                    and re.fullmatch(r'[\u3400-\u9fffA-Za-z0-9· .+\-]+', name.strip())})
    if clean:
        row = {'url': url, 'category': category, 'names': clean, 'retrieved': NOW}
        if detail:
            row['detail'] = detail
        ROWS.append(row)


def highway_names(soup, url):
    links = {}
    for anchor in soup.select('a[href]'):
        href = urljoin(url, anchor['href'])
        if urlparse(href).hostname != 'www.chinahighway.org' or not re.search(r'/view/\d+\.html$', href):
            continue
        # 使用链接的完整 title 而不是首页缩写，编号另存证据，不并入汉字词条。
        title = (anchor.get('title') or anchor.get_text(strip=True)).strip()
        title = re.sub(r'^[GS]\d+[A-Z]*\s*', '', title)
        if re.fullmatch(r'[\u3400-\u9fff]{2,16}高速公路', title):
            links[href] = title
    record(url, 'highways', links.values())
    record(url, 'highways', [name[:-2] for name in links.values()])
    return links


def collect_highways():
    home = 'https://www.chinahighway.org/'
    text, source = download(home)
    SOURCES.append(source)
    if not text:
        return
    soup = BeautifulSoup(text, 'html.parser')
    links = highway_names(soup, home)
    provinces = sorted({urljoin(home, anchor['href']) for anchor in soup.select('a[href]')
                        if '高速公路线路大全' in anchor.get_text() and '/view/' not in anchor['href']})
    # 全国和各省目录先完整读取，再访问详情页，避免靠猜测生成线路名。
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for url, result in zip(provinces, pool.map(download, provinces)):
            text, source = result
            SOURCES.append(source)
            if text:
                links.update(highway_names(BeautifulSoup(text, 'html.parser'), url))
    print('highway directories', len(provinces), 'detail links', len(links), flush=True)
    urls = sorted(links)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for url, result in zip(urls, pool.map(download, urls)):
            text, source = result
            SOURCES.append(source)
            if not text:
                continue
            soup = BeautifulSoup(text, 'html.parser')
            # 配套设施只取独立链接或表格单元格中的完整名称，不从新闻句子截取词尾。
            cells = [node.get_text(' ', strip=True) for node in soup.select('td, th')]
            cells.extend(node.get_text(' ', strip=True) for node in soup.select('a[href]')
                         if '/view/' in node['href'] and '/news/' not in node['href'])
            for category, suffix in [('toll_stations', '收费站'), ('service_areas', '(?:服务区|停车区)')]:
                names = []
                for cell in cells:
                    for part in re.split(r'[、,，;；/\n]', cell):
                        part = part.strip()
                        if re.fullmatch(r'[\u3400-\u9fff]{2,12}' + suffix, part):
                            names.append(part)
                record(url, category, names)
    print('highway detail responses', len(urls), flush=True)


def collect_music():
    urls = ['https://www.huaiyinjie.com/category/douyin/'] + [f'https://www.huaiyinjie.com/douyin/page/{n}' for n in range(2, 41)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for url, result in zip(urls, pool.map(download, urls)):
            text, source = result
            SOURCES.append(source)
            if not text:
                continue
            names = []
            for anchor in BeautifulSoup(text, 'html.parser').select('h2 a.post-title,h3 a.post-title'):
                name = re.split(r'\s+[–—-]\s+', anchor.get_text(strip=True), maxsplit=1)[0]
                name = re.sub(r'歌词$', '', name)
                # 仅接受原始完整标题；不把括号说明剪成未经核实的另一首作品。
                if len(name) % 2 == 0 and name[:len(name)//2] == name[len(name)//2:]:
                    continue
                names.append(name)
            record(url, 'song_titles', names, 'Third-party directory, not an official Douyin chart; article dates are not release dates.')
    url = 'https://music.baidu.com/album'
    text, source = download(url)
    SOURCES.append(source)
    if text:
        soup = BeautifulSoup(text, 'html.parser')
        for info in soup.select('.info'):
            name = info.select_one('.name')
            date = re.search(r'发行时间[：:]\s*(\d{4}-\d{2}-\d{2})', info.get_text(' ', strip=True))
            if name:
                record(url, 'album_titles', [name.get_text(strip=True)], date.group(1) if date else None)
    url = 'http://www.sina.cn/media/1820116475'
    text, source = download(url)
    SOURCES.append(source)
    if text:
        # 只提取作品书名号中的名称，不采集个人资料、联系方式或歌词。
        names = re.findall(r'《([^《》<>\n]{2,60})》', BeautifulSoup(text, 'html.parser').get_text(' ', strip=True))
        record(url, 'music', names, 'Music account posts; mention does not establish release date.')
    print('music directory pages', len(urls), flush=True)


def collect_movies():
    # 请求路径和字段已从网页公开加载脚本核实，不访问登录或私有接口。
    url = 'https://chinafilm.org.cn/api/base/outer/film/page'
    payloads = [{'yearMonth': f'2026-{month:02d}', 'filmName': ''} for month in range(1, 11)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for payload, result in zip(payloads, pool.map(lambda payload: download(url, payload), payloads)):
            text, source = result
            SOURCES.append(source)
            if not text:
                continue
            try:
                data = json.loads(text).get('data') or {}
                films = data.get('films') or {}
                if not isinstance(films, dict):
                    continue
                for date, entries in films.items():
                    record(url, 'film_titles', [item.get('name', item.get('filmName', '')) for item in entries], date)
            except (ValueError, AttributeError, TypeError) as error:
                source['parse_error'] = str(error)
    print('movie months requested', len(payloads), flush=True)


def main():
    collect_highways()
    collect_music()
    collect_movies()
    (OUT / 'expanded-page-names.json').write_text(json.dumps(ROWS, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {'retrieved': NOW, 'rows': len(ROWS), 'sources': SOURCES,
              'limits': 'Not exhaustive; historical roads may not be operating. Third-party music pages are not official social platform charts.'}
    (OUT / 'expanded-sources.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('expanded records', sum(len(row['names']) for row in ROWS), 'successful responses', sum('error' not in source for source in SOURCES), flush=True)


if __name__ == '__main__':
    main()
