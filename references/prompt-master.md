# 提示词母版 · 照片字母窗

> 三份母版：**§B 中文标准版**（默认用）、**§C 英文强化版**（图像模型对长中文失焦时用）、**§D 保真模式**（照片一个像素都不能动时用）。
> 填槽规则见 §A，翻车对照见 §E，禁止清单见 §F。

---

## §A 槽位表（八个槽，缺一个就塌）

| 槽 | 说明 | 取值来源 | 反面例子 |
|---|---|---|---|
| `主体` | 照片里到底是什么，名词堆叠 | 看原图 | "一只可爱的狗狗"（形容词无用） |
| `主体局部` | 字里要出现的那一块 | **能认出来的完整一块**（整张脸、整只爪、整个鞋头） | 「整个画面」（等于没取景）、「毛/石头/地面」（主体只剩一角） |
| `色值` | 下半部分纯色底 | `analyze` 的 `suggest_bg_dark` 或 `suggest_bg_paper` | 凭感觉写 #FFFFFF |
| `词` | 超粗大写英文单词 | 3-4 个字母，见 `diagnose.md` | 5 个以上、含中文 |
| `渗出部位` | 主体从字边探出去的那个部件 | 指名单一部件：一只前爪、一只耳朵、一个鞋头、一个球拍 | 「整个身体」「主体」——会漏成一整条边 |
| `标语` | 手写体一句话 | 2-3 个词，与情绪咬合 | "This is a photo" |
| `关键词行` | 底部两段疏排小字 | 左 `A / B / C`，右一句短语 | 写成完整长句 |
| `强调色` | 标语、线条、小图标的色 | 从原图捞，`suggest_accent` | 凭空加一个荧光色 |

**四条铁律**：词 3-4 个字母（示例 CATS / RUN / ACE / LENS 全是 3-4）；底色必须是**平涂的单一颜色**，且从原图同色系压暗；**字母笔画里就是照片**（不是墨块、不是半透明色）；字母之外除了探出的那个部件，不许再有照片。

**第五条的补充（用户反馈后加）**：字里的画面必须是**完整可辨的主体**，不是主体的碎片，也不是它脚下的地面。猫躺在地上时，字里要看得见猫的脸和身体，而不是猫上方那截墙面加下方那块石台。把 `<主体局部>` 写实——「两只猫熟睡的侧脸和前爪」比「猫」有效十倍。

**第六条的补充（字要"粗体大块"）**：只写"超粗"不够，模型会给你一个 Bold 就交差。必须写成 **black 级 / 木刻般的厚度 / 字腔还开着一小口 / 字母之间只留一道很细的深色缝**。字一细，深色的字腔就占了画面一半，小图上看就是"黑字铺在照片上"——方向做对了也会被读反。

**画布比例**：四个字母要顶天立地，天然需要 **1.9–2.0 : 1** 的横构图（参考图 1098×567 正好 1.94）。给 3:4 竖版，模型只能把字压成"中间一条"或者把字腔糊死，两种都救不回来。

**最容易翻车的理解（两个方向都错）**：
- 写成「字母镂空、透过字母能看见后面的照片，字是黑色的」→ 出来字是墨块，字里没画面。
- 写成「照片铺满整个画面、上面压字」→ 出来是一整块照片，字的边界没了。
正确的只有一句：**字母的笔画里是照片，字母以外是纯色底**，两者边界就是字形的轮廓。

**自检别靠眼睛**：这个版面天生有图底反转错觉——字母够粗时，深色的字腔会读成"实心黑字"，照片反而像背景。交付前**把某一个字母裁出来放大看**：A 的两条斜腿是毛 = 对，A 的三角内腔是深色 = 对。小图上看十次会错十次。

---

## §B 中文标准版（glyph · 默认主用）

> 版式目标：**整幅就是那个大字**。没有上下分栏，画面上不存在第二条照片带。
> 画布 **1.44 : 1**（参考图成片 529×368）。字母**不顶天立地**：占宽 90%、占高 57%，
> **上留 21% 给标语组、下留 22% 给垂下来的爪子**。这四条数字是量出来的，不是估的。

```
字体创意海报，横构图约 1.44:1，复古做旧印刷质感，胶片颗粒。

【版式·单栏】整幅画面只有一层结构：一个超大的英文全大写单词「<词>」立在深色底上。单词横向占画面九成宽、左右各留一点深色边；纵向只占画面中间约六成高——上方留出约两成画面的深色空档放标语，下方留出约两成空档让部件垂下来。画面不分栏、没有第二条照片带、没有分界线。

【底色】字母之外是纯色平涂的深底 <色值>，无渐变、无噪点、无图案、无光晕。

【核心·字里是照片】这个单词的**笔画内部就是照片**：不是墨块、不是色块、不是半透明压色，而是照片顺着字形轮廓被裁出来的样子。字里的内容是 <主体局部>，要完整、认得出。字母之间只留一道很细的深色缝；字母内部的空腔（A 的三角、C 与 S 的开口）是深色底，干净利落。

【字】字重极粗（black 级）、无衬线、略作压缩，**笔画横竖一样粗**（像木刻，不是把细体压扁的那种"竖细横粗"），字腔还开着（C 的碗、A 的三角、S 的两个口都要看得见）。不描边、不发光、不做浮雕、不加投影、字里不加任何墨色。

【第二层·渗出立体】这是最关键的一层：<渗出部位> 不老实待在字里，而是**越过字边**、横过字母之间的细缝，落在深色底上（一只前爪垂到字下、一只耳朵顶出字顶、一条腿从字母下沿伸出来），轮廓完整、边缘干净，看得出是同一个主体。它压在字母之上，是一层独立的东西——所以它在字母上、在缝里、在底色上都是连续的。除了这个部件，**主体的身体还可以在字的外轮廓外面露出一小片**（一条腿、一片毛、半只耳朵），让整幅画看得出是一整只动物而不是几个字块——但只许一小片，轮廓要连续，不许在字外铺成一条照片带。这是唯一允许出现在字母之外的照片内容。

【装饰·标语组】画面右上角，一行手写花体英文「<标语>」，倾斜约 -7 度，暖金色 <强调色>，笔画细、有轻重变化。它右边稍高处有一个**手绘小太阳**（一个圈加八道短射线，同色细线）；标语正下方有一道**与文字等长的细横线**。整组落在字母上方的空档里，不压到字。

【装饰·角落】画面左下角、字母下方，散落**两三枚小小的爪印**（一个掌垫加四颗脚趾），同色，大小相仿、略有错落。

【质感】复古做旧磨损：亮部发暖、暗部抬起来不发死（旧印片没有纯黑，最暗处也是暖褐色），表面有大小不一的斑块和轻微的划痕磨损；再覆一层明显胶片颗粒与极淡的半色调网点，像扫描下来的旧印刷品。**字母的轮廓也不完美**：边缘有缺墨、有溢墨，宽窄不一，像丝网版印歪了一点点，但字的骨架清清楚楚。颜色偏暖，不发灰、不发脏、不偏色。

【禁止】不要 3D 渲染、不要 C4D 材质、不要渐变光晕、不要金属反光、不要霓虹、不要多余装饰图形；不要胶带、贴纸、边框、水印、logo；除单词、标语以外不加任何文字，绝对不要出现汉字；**不要把单词做成空心描边字**，**不要让字母变成黑色实心块**，**不要把整幅铺满照片**——笔画里是照片，笔画外是纯色底；**不要让字母顶到画面上下边**，上下必须留出深色空档；**不要把字母边缘做成完美光滑的矢量曲线**，要带印刷的缺墨溢墨。
```

---

## §B2 分栏版（`--mode band` 才用）

上半照片、下半照片带压字的老版式。只在照片本身横长、需要画面在字间连续时用；其余情况一律用 §B。

```
一张上下分栏的复古电影海报，竖版 3:4，胶片印刷质感。

【版式】画面被一条水平直线严格切成两半，上半 50%，下半 50%。分界线水平、干净、不倾斜、不做撕纸边、不做渐变过渡。

【上半·照片】整幅实拍照片，顶格满铺左右上三边，无边框、无圆角、无白边、无投影。内容：<主体>。

【下半·照片带】一条横贯画面的连续照片带，画面内容与上半同源同机位。带子上立着一个超大的英文全大写单词「<词>」，字是这条照片带压暗后的样子（只压明度不压颜色），所以字与字之间、字腔里仍然是照片，画面是连的。

【渗出·立体】<渗出部位> 越过字边落到带子外，轮廓完整、边缘干净。

【装饰·三段】① 手写标语「<标语>」在右上角，倾斜 -7 度，颜色 <强调色>；② 底部左右两角各一行极小号疏排大写英文；③ 一条手绘曲线掠过字母表面（可选）。

【质感】胶片颗粒 + 极淡半色调网点 + 轻微褪色。

【禁止】同 §B：不要 3D、不要描边、不要汉字、不要贴纸边框。
```

---

## §C 英文强化版（模型对中文长提示词失焦时切这版）

```
Typographic poster, landscape about 1.44:1, distressed vintage print, 35mm grain.

LAYOUT — one single panel, no split, no second photo band, no horizon line. One enormous all-caps word "<WORD>" stands on the flat colour: about 90% of the frame width with a little margin either side, and only about 57% of the frame height, sitting in the middle. Roughly 21% of dark space stays above it for the caption group, and 22% below it for the part that hangs out. Not flush to the top or bottom edges.

BACKGROUND — one flat solid colour <hex> outside the letters. No gradient, no pattern, no glow, no noise.

CORE — **inside the letter strokes is the photograph itself**, cut along the glyph contours: not ink, not a flat fill, not a translucent tint. Inside the letters: <subject detail>, complete and recognisable. Between letters only a thin dark gutter; inside the counters (the A's triangle, the C's and S's apertures) it is the flat dark colour.

TYPE — ultra-black weight, sans-serif, slightly condensed, **horizontal and vertical strokes the same thickness** (like a woodcut, not a bold squeezed until its verticals went thin), counters still open (the C bowl, the A triangle, both S mouths). No outline, no bevel, no glow, no drop shadow, no ink tint inside the letterforms.

SECOND LAYER · ESCAPE — <escaping part> does not stay inside the letter. It crosses the letter edge, runs across the narrow gutters, and lands on the flat colour (a front paw hanging below the word, an ear breaking above the cap line, a leg sliding out from under the letters), with a clean complete contour that is obviously the same subject. It sits ON TOP of the letters and reads as one continuous layer across letter, gutter and flat colour. This is the ONLY photographic content allowed outside the letters.

DECOR —
1. Caption group, top right: handwritten script "<caption>", tilted about -7 degrees, warm gold <accent>, thin stroke; a small **hand-drawn sun** (circle plus eight short rays, same thin colour) sitting just above and to its right; a **thin rule the same width as the words** directly beneath it. The group sits in the dark space above the letters, never overlapping them.
2. Corner marks: two or three small **paw prints** (one pad plus four toes) scattered at the bottom left, below the letters, same colour, slightly offset from each other.

TEXTURE — distressed vintage print: warm highlights, lifted shadows, uneven mottled patches and light abrasion marks, plus strong 35mm grain and faint halftone dots. Warm grade, not washed out.

NEGATIVE — no 3D render, no C4D, no glow, no metal, no neon, no decorative shapes, no tape, no stickers, no border, no watermark, no logo, no extra text, absolutely no Chinese characters, no hollow outline letters, no black letterforms, no photo filling the whole frame — inside the strokes it is photo, outside them it is flat colour.
```

---

## §D 保真模式（照片不许被重绘时）

AI 一次成图永远会重绘照片。要求"必须是同一张照片"时，改走**程序合成**：

```bash
"$PY" "$SK" poster <图> --word LENS --bg "#6E1418" --window-zoom 1.3 \
  --tag "Shoot Film" --tag-pos tr --tag-color "214,150,90" \
  --rule-left "ANALOG / PATIENCE / GRAIN" --rule-right "36 FRAMES PER STORY" \
  -o poster.jpg
```

- 照片逐像素保真，文字绝不拼错，字里画面与上半部分严格同源同坐标系。
- 代价：主体能不能探出字边，取决于抠图质量与逐列凸出判定；抠不干净就只有干净的字母窗。
- 想要不规则穿插，再单独生成一个透明底的突破件叠回去（`image1` 传底图、`input_fidelity` 给 `high`）。

**判断标准**：用户说"效果炸" → 走 §B/§C；用户说"必须是原图 / 要印刷 / 不能变" → 走 §D。

---

## §E 翻车对照表（只改对应那一段，别整段重写）

| 症状 | 病因 | 补哪句 |
|---|---|---|
| 字母里是纯色，没照片 | 模型把"窗"理解成字体配色 | `字母笔画内部必须是照片，禁止纯色填充字形` |
| 字母里是一片模糊或虚化 | 模型拿背景填了字 | `字母里必须是主体本身（<主体局部>），不是天空、地面或背景` |
| 字里的照片和上方不是同一张 | 缺锚定 | `字母里的画面是上半部分照片的延续，同一机位同一焦距` |
| 字母有白边/发光/立体 | 模型默认审美 | `字母边缘就是照片边缘，直接切在底色上，不要描边` |
| 字是黑的/纯色块，字里没画面 | 模型把"大标题"当字体来做 | `字母笔画内部必须是照片本身，禁止任何墨色、纯色填充或半透明压色` |
| 底色上糊着一整片照片，字的边界没了 | 模型把"下半铺照片"当背景 | `字母以外必须是纯色底，除了探出的那个部件，底色上不许有任何影像` |
| 探出来的是一整条边，不是部件 | 没点名具体部件 | 把 `<渗出部位>` 写成一只前爪/一只耳/一个鞋头，不要写"主体" |
| 渗出的部件被字母切断，到了缝隙就断 | 模型把渗出层当成"字的颜色"处理 | 加 `它压在字母之上，是一层独立的东西，所以在字母上、在缝里、在底色上都是连续的` |
| 字太细，深色字腔占了一半画面 | 只写了"超粗" | 改 `black 级、木刻般的厚度、字腔只开一小口、字母之间只留一道很细的深色缝` |
| 字只占画面中间一条，上下两大块空 | 画布给了竖版 | 改横构图 1.9–2.0 : 1；或 `字母顶到上下左右四边，轻微出血` |
| 字母太小、像标题 | 词太长或宽度不够 | 换 3-4 字母的词；`96%` 改到 `100%`；加"可出血" |
| 出现汉字或乱码 | 未禁 | 加 `绝对不要出现任何汉字` |
| 只有大字没有装饰，像 PPT | 装饰段被模型忽略 | 把装饰拆成编号段重发，并强调"缺一不可" |
| 标语压在字母上糊成一团 | 模型不管层级 | `标语位于字母上方的空白区/右上角，不与字形重叠，被上边缘裁掉一点点` |
| 整体像 3D 渲染 | negative 不够 | 从 §F 抄全 |
| 照片边缘出现白框 | 漏了"无边框" | `照片顶格满铺，无边框无圆角` |

---

## §F 禁止清单（复制粘贴用）

```
no 3D render, no C4D, no bevel, no emboss, no drop shadow, no glow,
no metal, no neon, no glass, no gradient background, no bokeh overlay,
no white outline on letters, no hollow outline letters, no black letterforms,
no ink tint inside the letters, no photo filling the whole lower panel,
no second photograph on the flat colour, no sticker border,
no tape, no stickers, no frame, no watermark, no logo,
no extra text, no Chinese characters, no collage, no multiple photos,
no illustration, no vector-perfect doodles, no centered symmetrical template look
```
