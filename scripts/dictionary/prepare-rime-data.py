from pathlib import Path
import shutil
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'artifacts/rime-data'
OUT.mkdir(parents=True, exist_ok=True)

# 官方词典以繁体为主；打包时转换为简体，继续兼容应用现有简繁显示设置。
class Converter:
    def __init__(self):
        self.root = {}
        for name in ['TSCharacters.txt', 'TSPhrases.txt']:
            for line in (ROOT / 'third_party/librime/deps/opencc/data/dictionary' / name).read_text().splitlines():
                if not line or line.startswith('#') or '\t' not in line:
                    continue
                source, targets = line.split('\t', 1)
                node = self.root
                for character in source:
                    node = node.setdefault(character, {})
                node[''] = targets.split(' ')[0]
    def convert(self, text):
        result = []
        start = 0
        while start < len(text):
            node = self.root
            replacement, stop = text[start], start + 1
            for end in range(start, len(text)):
                node = node.get(text[end])
                if node is None:
                    break
                if '' in node:
                    replacement, stop = node[''], end + 1
            result.append(replacement)
            start = stop
        return ''.join(result)

converter = Converter()
from dictionary_policy import microplace_words, source_directory
excluded_microplaces = microplace_words(source_directory(ROOT))

# 英文词条权重给低一点：九宫格打数字时绝大多数是打中文，不能让 OK、Go 这类词把常用汉字顶下去；
# 全拼打 “ok” 因为没有中文读法，仍然会直接出 OK。
EN_WORD_WEIGHT = 50
EN_PHRASE_WEIGHT = 200

# 中英混输：雾凇拼音 cn_en 词表（OK啦、QQ音乐、U盘…）拆成“英文整段 + 汉字逐字拼音”的编码写进主词库，
# 同时把其中的英文词（OK、QQ、VIP…）单独收成词条，Rime 组句时就能拼出“OK的啦”这类没收录的说法。
import re
ENGLISH_SPELLINGS = set()
# “的啦/的呀”这类口语收尾原词库没有，组不出“OK的啦”，单独补上。
MIXED_PARTICLES = {'的啦': ('de la', 1500), '的呀': ('de ya', 1500), '的啊': ('de a', 1500),
                   '的吧': ('de ba', 1500), '的嘛': ('de ma', 1200), '的哦': ('de o', 1200)}
def mixed_entries(lines):
    syllables, known = set(), set()
    body = False
    for line in lines:
        if line == '...':
            body = True
        elif body and '\t' in line and not line.startswith('#'):
            columns = line.split('\t')
            known.add(columns[0])
            syllables.update(columns[1].split(' '))
    def split(code, count):
        if count == 0:
            return [] if not code else None
        for size in range(min(6, len(code)), 0, -1):
            if code[:size] in syllables:
                rest = split(code[size:], count - 1)
                if rest is not None:
                    return [code[:size]] + rest
        return None
    def pinyin_only(code):
        return code == '' or any(code[:k] in syllables and pinyin_only(code[k:]) for k in range(1, min(6, len(code)) + 1))
    phrases, words = {}, {}
    for line in (ROOT / 'third_party/rime-ice/cn_en.txt').read_text().splitlines():
        if line.startswith('#') or '\t' not in line:
            continue
        text, code = line.split('\t')
        if code != code.lower() or text in phrases:
            continue
        parts = re.findall(r'[A-Za-z]+|[\u4e00-\u9fff]+|.', text)
        position, codes = 0, []
        for index, part in enumerate(parts):
            if re.fullmatch('[A-Za-z]+', part):
                if code[position:position + len(part)] != part.lower():
                    break
                codes.append(part.lower())
                position += len(part)
                # 单字母和本身就是合法拼音的英文（如 pan）不单独成词，免得抢正常拼音。
                if len(part) >= 2 and not pinyin_only(part.lower()):
                    words.setdefault(part, part.lower())
            elif re.fullmatch('[\u4e00-\u9fff]+', part):
                following = parts[index + 1].lower() if index + 1 < len(parts) else ''
                end = len(code)
                if following:
                    end = next((e for e in range(len(code) - len(following), position, -1)
                                if code[e:e + len(following)] == following and split(code[position:e], len(part))), None)
                    if end is None:
                        break
                pieces = split(code[position:end], len(part))
                if not pieces:
                    break
                codes += pieces
                position = end
            else:
                break
        else:
            if position == len(code):
                phrases[text] = ' '.join(codes)
    for text, code in list(words.items()) + list(phrases.items()):
        ENGLISH_SPELLINGS.update(piece for piece in code.split(' ') if piece not in syllables)
    entries = [f'{text}\t{code}\t{EN_WORD_WEIGHT}' for text, code in sorted(words.items()) if text not in known]
    entries += [f'{text}\t{code}\t{EN_PHRASE_WEIGHT}' for text, code in sorted(phrases.items()) if text not in known]
    entries += [f'{text}\t{code}\t{weight}' for text, (code, weight) in MIXED_PARTICLES.items() if text not in known]
    # 九键数字里 “OK的吧” 若不是完整词条，Rime 会用单字拼出 “哦了恶霸” 这类不成句的结果。
    # 词表里已有 “英文+语气词”（OK啦、OK吗）的英文，补齐全部 “英文+的+语气词” 整词。
    particle_words = sorted({m.group(1) for text in phrases
                             for m in [re.fullmatch(r'([A-Za-z]+)[啦啊吧呀嘛哦了吗]', text)] if m})
    for word in particle_words:
        for particle, (particle_code, _) in MIXED_PARTICLES.items():
            combined = word + particle
            if combined not in known and combined not in phrases:
                entries.append(f'{combined}\t{word.lower()} {particle_code}\t{EN_PHRASE_WEIGHT}')
    return entries
essay = {}
for line in (ROOT / 'third_party/rime-essay/essay.txt').read_text().splitlines():
    text, weight = line.split('\t', 1)
    text = converter.convert(text)
    essay[text] = max(essay.get(text, 0), int(weight))

# 简体字形与古字形重合的读音不能用于现代词汇自动编码；原始上游文件保持不变。
modern_readings = {'荣': {'rong'}, '亏': {'kui'}, '吃': {'chi'}}
# 繁体词库里，“开 jian 95%”“么 yao”“儿 ren”这类是古字/异体字读音；繁转简后它们挂在常用简体字上，
# 会让 Rime 给“开店”等词组自动注出 jian dian。清单见 archaic-readings.tsv：权重降为 0%，
# 不参与词组自动注音，单字仍可输入。
archaic_readings = {tuple(line.split('\t')) for line in (ROOT / 'artifacts/archaic-readings.tsv').read_text().splitlines()
                    if line and not line.startswith('#')}
for dictionary, source in [('luna_pinyin', 'rime-luna-pinyin'), ('terra_pinyin', 'rime-terra-pinyin')]:
    lines = (ROOT / 'third_party' / source / (dictionary + '.dict.yaml')).read_text().splitlines()
    body = False
    output = []
    # 单字(字, 读音) -> output 下标及是否由繁体转换而来。
    # 繁转简会让“開→开”撞上词库原有的异体字“开 kai 0%”；Rime 只保留先出现的那条，
    # 导致常用读音权重为 0，打开/开心/关系等词组被注成错误读音。转换来的读音必须覆盖原条目。
    single = {}
    for line in lines:
        if body and '\t' in line and not line.startswith('#'):
            text, rest = line.split('\t', 1)
            converted = converter.convert(text)
            line = converted + '\t' + rest
            code = rest.split('\t', 1)[0]
            if len(converted) == 1:
                if converted in modern_readings and code.rstrip('12345') not in modern_readings[converted]:
                    continue
                if converted == text and (dictionary, converted, code) in archaic_readings:
                    line = converted + '\t' + code + '\t0%'
                key = (converted, code)
                from_traditional = converted != text
                if key in single:
                    index, previous_converted = single[key]
                    if from_traditional and not previous_converted:
                        output[index] = line
                        single[key] = (index, True)
                    continue
                single[key] = (len(output), from_traditional)
        output.append(line)
        if line == '...':
            body = True
    everyday_verbs = {
        '记下': ('ji xia', 'ji4 xia4'), '记住': ('ji zhu', 'ji4 zhu4'),
        '记好': ('ji hao', 'ji4 hao3'), '记清': ('ji qing', 'ji4 qing1'),
        '写下': ('xie xia', 'xie3 xia4'), '写好': ('xie hao', 'xie3 hao3'),
        '放下': ('fang xia', 'fang4 xia4'), '放好': ('fang hao', 'fang4 hao3'),
        '收好': ('shou hao', 'shou1 hao3'), '拿好': ('na hao', 'na2 hao3')}
    known_phrases = {line.split('\t', 1)[0] for line in output if '\t' in line}
    for phrase, codes in everyday_verbs.items():
        for suffix, suffix_codes in {'': ('', ''), '了': (' le', ' le5')}.items():
            text = phrase + suffix
            if text not in known_phrases:
                code_index = 0 if dictionary == 'luna_pinyin' else 1
                output.append(f'{text}\t{codes[code_index]}{suffix_codes[code_index]}\t20000')
            essay[text] = max(essay.get(text, 0), 200000)
    if dictionary == 'luna_pinyin':
        output += mixed_entries(output)
    supplement = ROOT / 'research/user-dictionary-20261022/rime.tsv'
    if supplement.is_file():
        known = {line.split('\t', 1)[0] for line in output if '\t' in line and not line.startswith('#')}
        added = 0
        with supplement.open(encoding='utf-8') as source:
            for line in source:
                text, plain, toned, weight = line.rstrip('\n').split('\t')
                if text not in known and text not in excluded_microplaces:
                    code = plain if dictionary == 'luna_pinyin' else toned
                    merged_weight = max(essay.get(text, 0), min(10, int(weight)))
                    output.append(f'{text}\t{code}\t{merged_weight}')
                    known.add(text)
                    added += 1
        print(f'{dictionary}: {added} user words added; existing entries preserved', flush=True)
    (OUT / (dictionary + '.dict.yaml')).write_text('\n'.join(output) + '\n')

(OUT / 'essay.txt').write_text(''.join(f'{text}\t{weight}\n' for text, weight in essay.items()))
shutil.copy2(ROOT / 'third_party/rime-essay/LICENSE', OUT / 'essay-LICENSE.txt')

pinyin = yaml.safe_load((ROOT / 'third_party/rime-luna-pinyin/pinyin.yaml').read_text())
zhuyin = yaml.safe_load((ROOT / 'third_party/rime-bopomofo/zhuyin.yaml').read_text())
full_algebra = pinyin['abbreviation']['__append']
zhuyin_algebra = sum((zhuyin[name]['__append'] for name in ['pinyin_to_zhuyin', 'free_order', 'abbreviation', 'keymap_bopomofo']), [])
ids = []
for mode in ['pinyin', 'nine', 'zhuyin', 'double']:
    for private in [False, True]:
        schema = 'glass_' + mode + ('_private' if private else '')
        ids.append(schema)
        alphabet = 'abcdefghijklmnopqrstuvwxyz'
        algebra = full_algebra
        dictionary = 'luna_pinyin'
        speller = {'alphabet': alphabet, 'delimiter': "'", 'algebra': algebra}
        translator = {'dictionary': dictionary, 'prism': 'glass_' + mode, 'user_dict': dictionary,
                      'enable_user_dict': not private, 'enable_sentence': True,
                      'enable_completion': True, 'initial_quality': 1,
                      'spelling_hints': 128, 'always_show_comments': True,
                      'enable_correction': mode == 'pinyin', 'sentence_fallback_only': True}
        if mode == 'nine':
            translator['sentence_fallback_only'] = True
            translator['spelling_hints'] = 128
            translator['always_show_comments'] = True
            speller['alphabet'] = '23456789abcdefghijklmnopqrstuvwxyz'
            # 保留字母拼写用于锁音，另派生数字拼写供九键解码。
            # 九键数字很容易恰好拼出 Go、IP、QQ 这类英文；若当完整拼音，Rime 会丢掉“功能、国内”等简拼整组。
            # 英文标成 fuzz 级别（九键没有其他模糊音）：内核据此既不让英文挤掉中文简拼，
            # 也不让中文全拼路径（653352=o le e la）删掉英文（ok de la）。
            english = '|'.join(sorted(ENGLISH_SPELLINGS))
            speller['algebra'] = pinyin['abbreviation']['__append'] + [
                f'xform/^({english})$/~$1/',
                'fuzz/^~([a-z]+)$/$1/',
                'erase/^~[a-z]+$/',
                'derive/^([a-z]+)$/\\U$1/',
                'xlit|ABCDEFGHIJKLMNOPQRSTUVWXYZ|22233344455566677778889999|']
        if mode == 'zhuyin':
            translator['dictionary'] = 'terra_pinyin'
            translator['user_dict'] = 'terra_pinyin'
            speller = {'alphabet': '1qaz2wsxedcrfv5tgbyhnujm8ik,9ol.0p;/- 6347',
                       'initials': '1qaz2wsxedcrfv5tgbyhnujm8ik,9ol.0p;/-',
                       'finals': ' 6347', 'delimiter': "'", 'use_space': True,
                       'algebra': zhuyin_algebra}
            translator['preedit_format'] = ["xlit|1qaz2wsxedcrfv5tgbyhnujm8ik,9ol.0p;/- 6347'|ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙㄧㄨㄩㄚㄛㄜㄝㄞㄟㄠㄡㄢㄣㄤㄥㄦˉˊˇˋ˙ |"]
        if mode == 'double':
            from runpy import run_path
            speller['algebra'] = run_path(str(ROOT / 'artifacts/prepare-double-pinyin.py'))['ALGEBRA']
            translator['enable_correction'] = False
        data = {'schema': {'schema_id': schema, 'name': 'GlassKeys ' + mode, 'version': '0.52'},
                'switches': [{'name': 'ascii_mode', 'reset': 0}],
                'engine': {'processors': ['speller', 'selector', 'navigator', 'express_editor'],
                           'segmentors': ['abc_segmentor', 'fallback_segmentor'],
                           'translators': ['script_translator'], 'filters': ['uniquifier']},
                'menu': {'page_size': 9}, 'speller': speller, 'translator': translator}
        (OUT / (schema + '.schema.yaml')).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
(OUT / 'default.yaml').write_text(yaml.safe_dump({'config_version': '0.52', 'schema_list': [{'schema': s} for s in ids]}, sort_keys=False))
for source, name in [('rime-luna-pinyin', 'luna-pinyin'), ('rime-terra-pinyin', 'terra-pinyin'), ('rime-bopomofo', 'bopomofo'), ('rime-ice', 'rime-ice')]:
    shutil.copy2(ROOT / 'third_party' / source / 'LICENSE', OUT / (name + '-LICENSE.txt'))
# 手机首次打开时 Rime 要把 8MB 文本词库编译成二进制，耗时数秒到十几秒。
# 这里用电脑版同一份引擎预先编译好，打进 assets/rime/build，手机直接加载；
# 若格式不兼容，Rime 会自动回退到现场编译，不会出错。
import subprocess, tempfile
prebuilt = OUT / 'build'
shutil.rmtree(prebuilt, ignore_errors=True)
with tempfile.TemporaryDirectory() as user_dir:
    subprocess.run([str(ROOT / 'artifacts/rime-explore'), str(OUT), user_dir, 'glass_nine', '9', '1'],
                   check=True, stdout=subprocess.DEVNULL)
    prebuilt.mkdir()
    for path in (Path(user_dir) / 'build').glob('*.bin'):
        shutil.copy2(path, prebuilt / path.name)
assert (prebuilt / 'luna_pinyin.table.bin').is_file(), 'Rime prebuilt dictionary missing'
for base in ['android', 'android oversea']:
    target = ROOT / base / 'app/src/main/assets/rime'
    target.mkdir(parents=True, exist_ok=True)
    for path in OUT.iterdir():
        if path.is_file():
            shutil.copy2(path, target / path.name)
    shutil.rmtree(target / 'build', ignore_errors=True)
    shutil.copytree(prebuilt, target / 'build')
print('Rime full/nine/zhuyin schemas and private variants packaged in both apps')
