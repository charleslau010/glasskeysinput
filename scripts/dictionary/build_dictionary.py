from pathlib import Path
import json
import re
import shutil
import unicodedata


def valid_text(text):
    # 偏旁和注音符号不能作为正常候选；独立成字的水、手、口、木仍然保留。
    components = '丨亅丿乀乁乚乛冂冖冫凵勹匚匸卩厶夂夊宀巛彐彑彡廴廾忄扌氵氺灬爫犭疒癶礻糹纟罒罓耂艹虍衤訁讠辶釒钅阝飠饣丬屮肀'
    return bool(text) and all(c not in components and not (
        0x2E80 <= ord(c) <= 0x2FFF or 0x3100 <= ord(c) <= 0x312F
        or 0x31A0 <= ord(c) <= 0x31BF or 0x31C0 <= ord(c) <= 0x31EF
    ) for c in text)


def build():
    root = Path(__file__).resolve().parents[2]
    target = Path(__file__).resolve().parents[1] / 'app/src/main/assets/pinyin.tsv'
    source_dir = root / 'research/dictionary-update-20261018'
    weighted = {}
    # 只从固定的原始来源生成，不读取上次产物，避免每次重建都改变频率。
    for line in (root / 'research/pinyin-source.txt').read_text(encoding='utf-8').splitlines():
        match = re.match(r'U\+([0-9A-F]+):\s*([^#]+)', line)
        if not match:
            continue
        code = int(match[1], 16)
        if not 0x4E00 <= code <= 0x9FFF:
            continue
        for spelling in match[2].strip().split(','):
            decomposed = unicodedata.normalize('NFD', spelling.replace('ü', 'v'))
            decomposed = decomposed.replace('u\u0308', 'v')
            plain = ''.join(c for c in decomposed if not unicodedata.combining(c))
            if re.fullmatch('[a-z]+', plain):
                weighted[(plain, chr(code))] = 1

    for filename in ('ice-base.dict.yaml', 'ice-ext.dict.yaml', 'ice-8105.dict.yaml'):
        for line in (source_dir / filename).read_text(encoding='utf-8-sig').splitlines():
            columns = line.split('\t')
            if len(columns) < 3 or line.startswith('#'):
                continue
            text, spelling, raw_weight = columns[:3]
            spelling = spelling.replace(' ', '')
            if not re.fullmatch('[a-z]+', spelling) or not raw_weight.isdigit():
                continue
            weight = int(raw_weight)
            if filename == 'ice-8105.dict.yaml':
                # 字频来自25亿字语料；按每千次缩放到基础词库的量级，保留真实相对频率。
                weight = max(1, round(weight / 1000))
                # 明确标注读音的常用字覆盖无频率兜底，不能被旧推导值抬高。
                weighted[(spelling, text)] = weight
            else:
                key = (spelling, text)
                weighted[key] = max(weighted.get(key, 1), weight)

    expansion = root / 'research/dictionary-expansion-20261018'
    added = duplicates = 0
    for line in (expansion / 'supplemental-pinyin.tsv').read_text(encoding='utf-8').splitlines():
        spelling, text, weight = line.split('\t')
        key = (spelling, text)
        if key in weighted:
            duplicates += 1
        elif valid_text(text):
            weighted[key] = int(weight)
            added += 1
    print(f'Expansion: {added} added, {duplicates} existing pronunciation/text pairs preserved')
    shutil.copyfile(expansion / 'brand-continuations.tsv', target.parent / 'brand-continuations.tsv')
    shutil.copyfile(expansion / 'wanxiang/LICENSE', target.parent / 'wanxiang-LICENSE.txt')
    shutil.copyfile(expansion / 'symspell/LICENSE', target.parent / 'symspell-LICENSE.txt')
    shutil.copyfile(expansion / 'manifest.json', target.parent / 'dictionary-expansion-sources.json')

    web = root / 'research/web-names-20261018'
    existing_text = {text for spelling, text in weighted}
    web_keys = set()
    web_added = web_existing = 0
    for line in (web / 'pinyin.tsv').read_text(encoding='utf-8').splitlines():
        spelling, text, weight = line.split('\t')
        if text in existing_text:
            web_existing += 1
            continue
        if not valid_text(text):
            continue
        weighted[(spelling, text)] = int(weight)
        web_keys.add((spelling, text))
        existing_text.add(text)
        web_added += 1
    import sys
    sys.path.insert(0, str(root / 'artifacts'))
    from dictionary_policy import microplace_words, source_directory
    excluded_microplaces = microplace_words(source_directory(root))
    user = root / 'research/user-dictionary-20261022'
    user_added = 0
    if (user / 'pinyin.tsv').is_file():
        with (user / 'pinyin.tsv').open(encoding='utf-8') as source:
            for line in source:
                spelling, text, weight = line.rstrip('\n').split('\t')
                if text not in existing_text and text not in excluded_microplaces and valid_text(text):
                    weighted[(spelling, text)] = min(10, int(weight))
                    existing_text.add(text)
                    user_added += 1
        shutil.copyfile(user / 'report.json', target.parent / 'user-dictionary-sources.json')
    print(f'User dictionary: {user_added} missing names added')
    english = {}
    english_sources = [expansion / 'supplemental-english.tsv', web / 'english.tsv']
    if (user / 'english.tsv').is_file():
        english_sources.append(user / 'english.tsv')
    for file in english_sources:
        for line in file.read_text(encoding='utf-8').splitlines():
            text, weight = line.split('\t')
            english.setdefault(text.lower(), (text, weight))
    (target.parent / 'english-expanded.tsv').write_text(''.join(f'{text}\t{weight}\n' for text, weight in english.values()), encoding='utf-8')
    shutil.copyfile(web / 'report.json', target.parent / 'web-name-sources.json')
    report = {'web_added': web_added, 'web_existing_ignored': web_existing, 'web_added_pairs': sorted(web_keys)}
    (web / (Path(__file__).resolve().parents[1].name.replace(' ', '-') + '-merge.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Web collection: {web_added} names added, {web_existing} existing names ignored')

    # 日常对话词适度提权，只调整上游已存在的词条，不虚构语料频次。
    conversational = {'你好', '谢谢', '再见', '我们', '你们', '可以', '好的', '没关系',
                      '知道', '不知道', '今天', '明天', '现在', '已经', '工作', '怎么',
                      '为什么', '什么', '没问题', '不好意思', '辛苦了', '收到', '马上', '稍等'}
    promoted = 0
    for key in weighted:
        if key[1] in conversational:
            weighted[key] = min(2000000000, weighted[key] * 4)
            promoted += 1
    weighted = {key: weight for key, weight in weighted.items() if valid_text(key[1])}
    print(f'Conversational priority adjusted for {promoted} existing entries')
    # 同频时也固定次序，使源码、重复构建和APK里的词库能够逐字节核对。
    ordered = sorted(weighted.items(), key=lambda item: (-item[1], item[0]))
    target.write_text(''.join(f'{spelling}\t{text}\t{weight}\n'
                              for (spelling, text), weight in ordered), encoding='utf-8')
    # 常用高频词加全部单字组成启动词库，全量词库后台就绪前仍可正常选字。
    starter = ordered[:3000] + [item for item in ordered[3000:] if len(item[0][1]) == 1]
    (target.parent / 'pinyin-starter.tsv').write_text(
        ''.join(f'{spelling}\t{text}\t{weight}\n' for (spelling, text), weight in starter), encoding='utf-8')
    shutil.copyfile(root / 'research/pinyin-data-LICENSE.txt', target.parent / 'pinyin-data-LICENSE.txt')
    shutil.copyfile(source_dir / 'upstream-LICENSE', target.parent / 'rime-ice-LICENSE.txt')
    (target.parent / 'dictionary-sources.txt').write_text(
        'Pinyin data: https://github.com/mozillazg/pinyin-data (MIT)\n'
        'Character and phrase dictionaries: https://github.com/iDvel/rime-ice '
        'cn_dicts/8105.dict.yaml, base.dict.yaml, ext.dict.yaml (GPL-3.0).\n'
        'Source commit: da1fbe602e38f26db846fa10120ee64c2b0324c0 (2026-10-05). Retrieved: 2026-10-18.\n'
        'Vendored sources: research/dictionary-update-20261018/. Rebuild with this project tools/build_dictionary.py.\n'
        'Character counts divided by 1000; 24 conversational terms use a 4x ranking multiplier, not measured corpus counts.\n', encoding='utf-8')
    print(f'Bundled {len(weighted)} weighted offline dictionary entries')


if __name__ == '__main__':
    try:
        build()
    except (OSError, ValueError) as error:
        raise SystemExit(f'词库生成失败：{error}') from error
