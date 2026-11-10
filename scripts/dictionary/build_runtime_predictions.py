from pathlib import Path
import heapq


def build():
    assets = Path(__file__).resolve().parents[1] / 'app/src/main/assets'
    selected = []
    syllables = set()
    with (assets / 'pinyin.tsv').open(encoding='utf-8') as source:
        for line in source:
            fields = line.rstrip('\n').split('\t')
            if len(fields) < 2:
                continue
            spelling, text = fields[:2]
            if len(text) == 1 and len(spelling) <= 6:
                syllables.add(spelling)
            if not 2 <= len(text) <= 8:
                continue
            weight = int(fields[2]) if len(fields) > 2 else 1
            item = (weight, text, spelling)
            if len(selected) < 50000:
                heapq.heappush(selected, item)
            elif item > selected[0]:
                heapq.heapreplace(selected, item)
    words = {}
    for weight, text, spelling in selected:
        words[text] = max(weight, words.get(text, 0))
    with (assets / 'runtime-predictions.tsv').open('w', encoding='utf-8') as output:
        for text, weight in sorted(words.items()):
            output.write(f'{text}\t{weight}\n')
    (assets / 'runtime-syllables.txt').write_text('\n'.join(sorted(syllables)) + '\n', encoding='utf-8')
    print(f'Runtime predictions: {len(words)} words; {len(syllables)} syllables')


if __name__ == '__main__':
    build()
