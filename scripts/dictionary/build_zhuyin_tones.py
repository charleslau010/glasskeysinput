from pathlib import Path
import re
import unicodedata


def build():
    root = Path(__file__).resolve().parents[2]
    tones = {}
    marks = {'\u0304': 1, '\u0301': 2, '\u030c': 3, '\u0300': 4}
    for line in (root / 'research/pinyin-source.txt').read_text(encoding='utf-8').splitlines():
        match = re.match(r'U\+([0-9A-F]+):\s*([^#]+)', line)
        if not match:
            continue
        point = int(match[1], 16)
        for pronunciation in match[2].strip().split(','):
            decomposed = unicodedata.normalize('NFD', pronunciation.replace('ü', 'v')).replace('u\u0308', 'v')
            tone = next((marks[c] for c in decomposed if c in marks), 5)
            spelling = ''.join(c for c in decomposed if not unicodedata.combining(c))
            if re.fullmatch('[a-z]+', spelling):
                key = (point, spelling)
                tones[key] = tones.get(key, 0) | (1 << tone)
    content = ''.join(f'{point}\t{spelling}\t{mask}\n' for (point, spelling), mask in sorted(tones.items()))
    for project in ('android', 'android oversea'):
        target = root / project / 'app/src/main/assets/zhuyin-tones.tsv'
        target.write_text(content, encoding='utf-8')
    print(f'Generated {len(tones)} tone entries for both projects')


if __name__ == '__main__':
    try:
        build()
    except (OSError, ValueError) as error:
        raise SystemExit(f'注音声调表生成失败：{error}') from error
