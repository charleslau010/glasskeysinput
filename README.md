# Glass Keys 输入法 · 词库

Glass Keys 是一款免费的 Android 中文输入法：离线输入，支持九宫格、全键盘、双拼、笔画、注音和繁体，带本地学习与整句输入。

- 官网与下载：<https://glasskeysinput.online>
- 输入法本身是免费软件，**不开源**；本仓库只公开它使用的**词库数据**、**生成词库的脚本**和**第三方授权**。

## 为什么公开词库

输入法的拼音词库由多个开源项目的数据整理而成，其中包括 GPL-3.0 授权的 [rime-ice 雾凇拼音](https://github.com/iDvel/rime-ice)、LGPL-3.0 授权的 Rime 官方词典，以及 ODbL、CC BY-SA 等要求“相同方式共享”的数据。按照这些授权的要求，这里公开由它们加工而成的词库文件和生成方法，并保留原始授权。这些词库文件按各自来源的授权提供，详见 `licenses/`。

## 目录

| 路径 | 内容 |
|---|---|
| `dictionaries/pinyin.tsv` | 主拼音词库：`拼音<TAB>词语<TAB>词频`，约 160 万条 |
| `dictionaries/pinyin-starter.tsv` | 启动时先加载的常用词小词库 |
| `dictionaries/english-expanded.tsv` | 英文单词补全与中英混输词表 |
| `dictionaries/runtime-predictions.tsv` | 上屏后的联想词 |
| `dictionaries/zhuyin-tones.tsv` | 注音声调 |
| `dictionaries/stroke.dict.yaml` | 笔画输入词典 |
| `dictionaries/rime/` | Rime 明月拼音、地球拼音词典与 essay 词频 |
| `sources/全部词条_去重汇总.txt` | 专有名词词表（地名、道路、车站、景区、人物、品牌、作品、网络用语等，约 153 万条），说明见 `sources/词表说明.md` |
| `scripts/dictionary/` | 把上述来源合并、换算成输入法词库的脚本 |
| `scripts/names/` | 整理专有名词词表的脚本与人工整理清单 |
| `licenses/` | 各来源的授权全文与来源清单 |

## 来源与授权

| 来源 | 用途 | 授权 |
|---|---|---|
| [rime-ice 雾凇拼音](https://github.com/iDvel/rime-ice) | 主要字词、词频、英文词典 | GPL-3.0 |
| [Rime](https://github.com/rime) 明月拼音、地球拼音、essay | Rime 词典与词频 | LGPL-3.0 |
| 笔画词典 | 笔画输入 | LGPL-3.0 |
| [万象拼音 rime_wanxiang](https://github.com/amzxyz/rime_wanxiang) | 补充词条 | CC BY 4.0 |
| [pinyin-data](https://github.com/mozillazg/pinyin-data) | 汉字拼音 | MIT |
| [SymSpell](https://github.com/wolfgarbe/SymSpell) | 拼写纠错算法 | MIT |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | 地名、道路、景点 | © OpenStreetMap contributors，ODbL 1.0 |
| [Wikidata](https://www.wikidata.org) | 人物、品牌、作品、车站等 | CC0 1.0 |
| [中文维基百科](https://zh.wikipedia.org) | 景区、交通线路、网络用语等列表 | CC BY-SA 4.0 |
| [萌娘百科](https://zh.moegirl.org.cn)（经 [mw2fcitx](https://github.com/outloudvi/mw2fcitx)） | ACG 与网络小众词条标题 | CC BY-NC-SA 3.0 |
| [fcitx5-pinyin-zhwiki](https://github.com/felixonmars/fcitx5-pinyin-zhwiki) web-slang | 网络用语 | Unlicense（源自维基百科，CC BY-SA） |
| [THUOCL 清华开放中文词库](https://github.com/thunlp/THUOCL) | 汽车、IT、历史名人 | MIT |
| 国家统计局区划代码（经 [modood/Administrative-divisions-of-China](https://github.com/modood/Administrative-divisions-of-China)） | 省市区县乡镇村 | WTFPL |
| 12306 公开车站名表、公开报道、人工整理 | 车站、新词、热梗 | — |

由 OpenStreetMap 衍生的地名词表按 ODbL 1.0 提供；由 GPL-3.0、LGPL-3.0 数据加工的词库文件按原授权提供。

输入法中的整句语言模型、离线听写模型及其授权说明，请在输入法“设置 › 更新支持 › 隐私与说明 › 开源组件与授权”中查看。

## 反馈

词库有错误或授权问题，欢迎提交 Issue。
