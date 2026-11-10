"""将完整中文词库和用户分类词库生成磁盘联想索引，不增加手机全量内存词表。"""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]+')
MIXED = re.compile(r'([\u3400-\u4dbf\u4e00-\u9fff]{2,12})([A-Za-z][A-Za-z0-9 .+\-]{0,23})')


def category_words(source):
    # 只读取词条代码块，避免把目录、来源说明当成词导入。
    for path in sorted(source.rglob('*.md')):
        active = False
        priority = 0
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.startswith('## '):
                priority = 0 if any(name in line for name in ('Wikidata', 'THUOCL')) else (2 if any(name in line for name in ('品牌', '汽车集团')) else 1)
            if line.strip().startswith('```'):
                active = not active
            elif active and line.strip():
                yield path.relative_to(source).as_posix(), line.strip(), priority


def build(source):
    out = ROOT / 'research/dictionary-audit-20261023'
    out.mkdir(parents=True, exist_ok=True)
    temporary = out / 'prediction-work.sqlite'
    if temporary.exists():
        raise ValueError('已有中间索引，避免覆盖；请检查上次生成结果')
    database = sqlite3.connect(temporary)
    database.execute('PRAGMA journal_mode=OFF')
    database.execute('PRAGMA synchronous=OFF')
    database.execute('CREATE TABLE words(text TEXT PRIMARY KEY, weight INTEGER NOT NULL) WITHOUT ROWID')
    batch = []
    with (ROOT / 'android/app/src/main/assets/pinyin.tsv').open(encoding='utf-8') as stream:
        for line in stream:
            _, text, weight = line.rstrip('\n').split('\t')
            if HAN.fullmatch(text) and 2 <= len(text) <= 16:
                batch.append((text, int(weight)))
            if len(batch) >= 10000:
                database.executemany('INSERT INTO words VALUES (?,?) ON CONFLICT(text) DO UPDATE SET weight=max(weight,excluded.weight)', batch)
                batch.clear()
    database.executemany('INSERT INTO words VALUES (?,?) ON CONFLICT(text) DO UPDATE SET weight=max(weight,excluded.weight)', batch)
    coverage = {}
    mixed = set()
    missing = set()
    curated = {}
    for category, text, priority in category_words(source):
        curated[text] = max(priority, curated.get(text, 0))
        stats = coverage.setdefault(category, {'words': 0, 'pure_han': 0, 'existing': 0, 'missing': 0, 'mixed_continuations': 0, 'other_format': 0})
        stats['words'] += 1
        if HAN.fullmatch(text) and 2 <= len(text) <= 16:
            stats['pure_han'] += 1
            if database.execute('SELECT 1 FROM words WHERE text=?', (text,)).fetchone():
                stats['existing'] += 1
            else:
                stats['missing'] += 1
                missing.add(text)
                # 未通过原始拼音/格式核验的词仅列入缺口报告，不绕过上次质量过滤。
        elif MIXED.fullmatch(text):
            mixed.add(text)
            stats['mixed_continuations'] += 1
            database.execute('INSERT OR IGNORE INTO words VALUES (?,100)', (text,))
        else:
            stats['other_format'] += 1
    database.commit()
    database.execute('CREATE TABLE raw(prefix TEXT, next TEXT, weight INTEGER, priority INTEGER)')
    batch = []
    for text, weight in database.execute('SELECT text,weight FROM words'):
        match = MIXED.fullmatch(text)
        if match:
            rows = [(match[1], match[2], weight, curated.get(text, 0))]
        else:
            # 保持现有最多续接四字的行为；长词只索引可输出的尾部。
            rows = [(text[:i], text[i:], weight, curated.get(text, 0)) for i in range(max(1, len(text)-4), min(len(text), 13))]
        batch.extend(rows)
        if len(batch) >= 10000:
            database.executemany('INSERT INTO raw VALUES (?,?,?,?)', batch)
            batch.clear()
    database.executemany('INSERT INTO raw VALUES (?,?,?,?)', batch)
    database.commit()
    target = out / 'prediction-index.sqlite'
    if target.exists():
        raise ValueError('输出索引已存在，不覆盖已有归档')
    database.execute('ATTACH DATABASE ? AS result', (str(target),))
    database.execute('CREATE TABLE result.predictions(prefix TEXT, next TEXT, weight INTEGER, priority INTEGER, PRIMARY KEY(prefix,weight DESC,priority DESC,next)) WITHOUT ROWID')
    database.execute('INSERT INTO result.predictions SELECT prefix,next,weight,priority FROM (SELECT prefix,next,weight,priority,row_number() OVER (PARTITION BY prefix,priority ORDER BY weight DESC,next) AS rank FROM raw) WHERE rank<=CASE priority WHEN 0 THEN 36 ELSE 6 END')
    database.commit()
    count, prefixes = database.execute('SELECT count(*),count(DISTINCT prefix) FROM result.predictions').fetchone()
    examples = {prefix: database.execute('SELECT next,weight FROM result.predictions WHERE prefix=? ORDER BY weight DESC,priority DESC,next LIMIT 48', (prefix,)).fetchall() for prefix in ('我','你','今天','工作','我们','北京','问','享','问界','享界')}
    database.close()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    report = {'source': str(source), 'categories': coverage, 'category_missing_pure_han_pending_review': len(missing), 'mixed_models_indexed': len(mixed), 'prediction_rows': count, 'prefixes': prefixes, 'bytes': target.stat().st_size, 'sha256': digest, 'examples': examples, 'limits': '联想每前缀最多48项，纯中文续接最多4字；混写仅支持中文前缀+英文数字尾部。不把分类说明当成词条，不生成混写拼音。'}
    (out / 'coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out / 'missing-pure-han.txt').write_text('\n'.join(sorted(missing))+'\n', encoding='utf-8')
    print(json.dumps({key: value for key,value in report.items() if key != 'categories'}, ensure_ascii=False, indent=2), flush=True)
    # 安装相同索引与内容版本标记，升级时不复用旧的解压副本。
    import shutil
    for base in ('android', 'android oversea'):
        assets = ROOT / base / 'app/src/main/assets'
        shutil.copyfile(target, assets / 'prediction-index.sqlite')
        (assets / 'prediction-index-version.txt').write_text(digest+'\n', encoding='ascii')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    try:
        build(args.source)
    except (OSError, ValueError, sqlite3.Error) as error:
        raise SystemExit(f'联想索引生成失败：{error}') from error
