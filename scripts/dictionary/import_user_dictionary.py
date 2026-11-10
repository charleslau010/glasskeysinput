"""将用户纯文本词库转为可追溯的补充源；不修改用户原文件。"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/web-names-20261018/python-deps'))
from pypinyin import Style, lazy_pinyin

OUT = ROOT / 'research/user-dictionary-20261022'


def import_dictionary(source):
    OUT.mkdir(parents=True, exist_ok=True)
    existing = set()
    existing_codes = {}
    for base in ('android', 'android oversea'):
        assets = ROOT / base / 'app/src/main/assets'
        with (assets / 'pinyin.tsv').open(encoding='utf-8') as stream:
            for line in stream:
                code, text, weight = line.rstrip('\n').split('\t')
                existing.add(text)
                existing_codes.setdefault(text, code)
        with (assets / 'english-expanded.tsv').open(encoding='utf-8') as stream:
            existing.update(line.split('\t')[0].casefold() for line in stream)
    counts = Counter()
    seen = set()
    digest = hashlib.sha256()
    # 独立补充源避免重跑旧采集器覆盖新词；低权重不冒充真实使用频率。
    with source.open('rb') as stream, (OUT / 'pinyin.tsv').open('w', encoding='utf-8') as chinese, \
            (OUT / 'english.tsv').open('w', encoding='utf-8') as english, \
            (OUT / 'rime.tsv').open('w', encoding='utf-8') as rime, \
            (OUT / 'review.tsv').open('w', encoding='utf-8') as review:
        for raw in stream:
            digest.update(raw)
            counts['source_lines'] += 1
            text = raw.decode('utf-8-sig').strip()
            if not text:
                counts['blank'] += 1
                continue
            key = text.casefold() if text.isascii() else text
            if key in seen:
                counts['source_duplicates'] += 1
                continue
            seen.add(key)
            if re.fullmatch(r'[A-Za-z]{2,32}', text):
                if key in existing:
                    counts['english_existing'] += 1
                else:
                    english.write(f'{text}\t50\n')
                    counts['english_added'] += 1
                # 英文候选进入英文键盘，不增加九键英文歧义。
                continue
            if not re.fullmatch(r'[\u3400-\u4dbf\u4e00-\u9fff]{2,24}', text):
                counts['review_format'] += 1
                review.write(f'unsupported_format\t{text}\n')
                continue
            if any(char in text for char in '×某〇○'):
                counts['review_placeholder'] += 1
                review.write(f'placeholder\t{text}\n')
                continue
            syllables = lazy_pinyin(text, style=Style.NORMAL, errors=lambda chars: list(chars), strict=True)
            tones = lazy_pinyin(text, style=Style.TONE3, neutral_tone_with_five=True,
                                errors=lambda chars: list(chars), strict=True)
            syllables = [code.replace('ü', 'v') for code in syllables]
            tones = [code.replace('ü', 'v') for code in tones]
            if not all(re.fullmatch('[a-z]+', code) for code in syllables) or not all(
                    re.fullmatch('[a-z]+[1-5]', code) for code in tones):
                counts['review_pronunciation'] += 1
                review.write(f'unencoded\t{text}\n')
                continue
            code = ''.join(syllables)
            if text in existing:
                counts['chinese_existing'] += 1
            else:
                chinese.write(f'{code}\t{text}\t100\n')
                counts['chinese_added'] += 1
            # Rime 原词库和备用 TSV 独立判重，已有词也可能需要补进原生引擎。
            if text in existing_codes and existing_codes[text] != code:
                counts['review_existing_pronunciation'] += 1
                review.write(f'pronunciation_conflict\t{text}\t{code}\t{existing_codes[text]}\n')
                continue
            rime.write(f'{text}\t{" ".join(syllables)}\t{" ".join(tones)}\t100\n')
            counts['rime_source_entries'] += 1
    report = {
        'source': str(source), 'source_sha256': digest.hexdigest(), 'counts': dict(counts),
        'pypinyin_version': '0.55.0', 'weights': {'chinese': 100, 'english': 50},
        'limits': '拼音和声调由机器生成，未逐条人工核验；特殊字符、数字混写、超长词和读音冲突进入 review.tsv，不自动入库。英文只加入英文键盘。',
    }
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    try:
        import_dictionary(args.source)
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit(f'词库导入失败：{error}') from error
