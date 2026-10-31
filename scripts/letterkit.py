#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
letterkit.py — 照片字母窗海报排版引擎
所属技能：photo-letter-window

四个子命令：
  prep     照片预处理（EXIF 转正 / sRGB / 长边压缩），产出干净的源图
  analyze  读图体检 + 真实主色提取 + 底色建议（不瞎编颜色）
  palette  只出配色
  poster   程序合成「上下分栏 + 字母照片窗 + 主体压边 + 三层装饰」

设计要点（别改坏）：
  1. 字母窗里的照片 = 同一张原图 cover 到整张画布后的对应区域，
     与上半部分天然同源、同坐标系、同颗粒 —— 这是本效果立身之本。
  2. 字母默认无描边（示例图即如此），字形靠「膨胀加粗 + 水平压缩」逼近超粗压缩体。
  3. 字母顶天立地：字高不足时自动放大到超出血，宽度允许溢出画布。
  4. 照片层最后贴回画布顶部（压住字母上沿），产生「前后穿插」。
  5. 装饰三层：手写标语、底部关键词行（宽字距）、手绘线条（最上层）。
"""

import argparse
import colorsys
import json
import math
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageFilter, ImageChops
except ImportError:
    sys.exit("[x] 缺少 Pillow：pip install pillow")

# ---------------------------------------------------------------- 字体候选
DISPLAY_FONTS = [                       # 主字形：超粗衬线
    r"C:\Windows\Fonts\georgiab.ttf",
    r"C:\Windows\Fonts\timesbd.ttf",
    r"C:\Windows\Fonts\ariblk.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]
GLYPH_FONTS = [                         # glyph 主字形：必须本身就是 Black 字重
    r"C://Windows//Fonts//ariblk.ttf",   # Arial Black——字腔还开着，膨胀一点就够
    r"C://Windows//Fonts//seguibl.ttf",
    r"C://Windows//Fonts//impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
SCRIPT_FONTS = [                        # 手写标语
    r"C:\Windows\Fonts\segoepr.ttf",
    r"C:\Windows\Fonts\Inkfree.ttf",
    r"C:\Windows\Fonts\georgiai.ttf",
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
]
SANS_FONTS = [                          # 底部小字
    r"C:\Windows\Fonts\bahnschrift.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _first(paths, explicit=None):
    if explicit and Path(explicit).exists():
        return str(explicit)
    for f in paths:
        if Path(f).exists():
            return f
    return None


def pick_font(explicit=None, glyph=False):
    """glyph 要的是"粗体大块"，用字体自带的 Black 字重；
    拿 Georgia Bold 靠 MaxFilter 硬吹，衬线会被撑成团块，字自己就不见了。"""
    f = _first(GLYPH_FONTS if glyph else DISPLAY_FONTS, explicit)
    if not f:
        raise SystemExit("[x] 找不到可用字体，用 --font 指定一个 .ttf/.otf 路径")
    return f


# ---------------------------------------------------------------- prep
def cmd_prep(a):
    src = Path(a.image)
    if not src.exists():
        sys.exit(f"[x] 文件不存在：{src}")

    im = Image.open(src)
    im = ImageOps.exif_transpose(im)          # 手机竖拍不再躺倒
    im = im.convert("RGB")                     # 清 HEIC/RGBA/CMYK 隐患

    w, h = im.size
    s = a.maxlong / max(w, h)
    if s < 1:
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=95, subsampling=1)

    print(json.dumps({
        "out": str(out),
        "size": f"{im.width}x{im.height}",
        "orientation": "portrait" if im.height > im.width else ("square" if im.width == im.height else "landscape"),
        "aspect": round(im.width / im.height, 3),
    }, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 取色
def _dominant(im, n):
    small = im.copy()
    small.thumbnail((260, 260), Image.LANCZOS)
    q = small.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], key=lambda x: -x[0])
    total = sum(c for c, _ in counts) or 1
    out = []
    for cnt, idx in counts:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        out.append({"hex": "#%02X%02X%02X" % (r, g, b), "share": round(cnt / total, 3),
                    "rgb": [r, g, b]})
    return out


def _lum(rgb):
    r, g, b = [c / 255 for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _sat(rgb):
    mx, mn = max(rgb), min(rgb)
    return 0 if mx == 0 else (mx - mn) / mx


def _tone(rgb, value, sat_mul=0.75):
    """保留色相，把明度压到 value、饱和度打折 —— 造「沉下去的同色系底色」。"""
    h, s, v = colorsys.rgb_to_hsv(*[c / 255 for c in rgb])
    r, g, b = colorsys.hsv_to_rgb(h, min(1.0, s * sat_mul), value)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def cmd_analyze(a):
    im = Image.open(a.image)
    im = ImageOps.exif_transpose(im).convert("RGB")

    gray = im.convert("L")
    px = list(gray.resize((160, 160)).get_flattened_data())
    mean = sum(px) / len(px)
    std = (sum((p - mean) ** 2 for p in px) / len(px)) ** 0.5

    doms = _dominant(im, a.colors)
    darkest = min(doms, key=lambda d: _lum(d["rgb"]))
    lightest = max(doms, key=lambda d: _lum(d["rgb"]))
    vivid = max(doms, key=lambda d: _sat(d["rgb"]) * 0.6 + d["share"] * 0.4)
    tint = max(doms, key=lambda d: _sat(d["rgb"]) * 0.7 + _lum(d["rgb"]) * 0.3)

    w, h = im.size
    report = {
        "size": f"{w}x{h}",
        "orientation": "portrait" if h > w else ("square" if w == h else "landscape"),
        "aspect": round(w / h, 3),
        "brightness": round(mean / 255, 3),
        "contrast": round(std / 255, 3),
        "dominant_colors": doms,
        "suggest_bg_dark": _tone(tint["rgb"], 0.16),      # 沉下去的同色系深底
        "suggest_bg_mid": _tone(tint["rgb"], 0.30),
        "suggest_bg_paper": "#F2E8D5",                     # 原文米白纸色
        "suggest_accent": vivid["hex"],
        "suggest_dark": darkest["hex"],
        "suggest_light": lightest["hex"],
        "advice": [],
    }
    if h <= w:
        report["advice"].append("横图/方图：cover 到 3:4 会左右各裁约 30%，主体贴边的构图先手动裁好。")
    if mean / 255 < 0.28:
        report["advice"].append("画面偏暗：底色走 suggest_bg_paper（米白），别用深底，否则整体糊成一团。")
    if mean / 255 > 0.75:
        report["advice"].append("画面偏亮：底色走 suggest_bg_dark，米白底会让分界线消失。")
    if std / 255 < 0.12:
        report["advice"].append("平淡低对比：--window-zoom 1.25 拉近主体局部，制造局部张力。")
    if not report["advice"]:
        report["advice"].append("素材条件良好，可直接进入排版。")

    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_palette(a):
    im = Image.open(a.image)
    im = ImageOps.exif_transpose(im).convert("RGB")
    print(json.dumps({"colors": [d["hex"] for d in _dominant(im, 8)]}, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 文字
def _fit_size(word, target_w, font_path):
    lo, hi, best = 8, 4000, 8
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(font_path, mid)
        b = probe.textbbox((0, 0), word, font=f)
        if b[2] - b[0] <= target_w:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _wear_edge(mask, amount, seed=7):
    """字形边缘做旧：边界上下随机长出去、随机被咬掉一点，像印歪了的丝网版。

    干净的矢量边一眼就露是现代软件排的。参考图的字边是毛的：有缺墨、有溢墨，
    宽窄不一，靠这个才像"老海报"。做法是把字形当成一条等高线，用噪声去推它——
    噪声大的地方边界往里退，噪声小的地方往外长，退进/长出量不超过 amount 像素。
    """
    if amount <= 0:
        return mask
    try:
        import numpy as np
        from scipy.ndimage import distance_transform_edt
    except ImportError:
        return mask
    a = np.asarray(mask) > 128
    if not a.any():
        return mask
    H, W = a.shape
    rs = np.random.RandomState(seed)
    # 低频块（8px 一格）+ 高频颗粒：只用低频会变成均匀波浪，只用高频会成砂纸
    cell = 4
    low = rs.rand(H // cell + 2, W // cell + 2).astype(np.float32)
    low = np.kron(low, np.ones((cell, cell), np.float32))[:H, :W]
    high = rs.rand(H, W).astype(np.float32)
    field = 0.55 * low + 0.45 * high
    din = distance_transform_edt(a)
    dout = distance_transform_edt(~a)
    signed = np.where(a, din, -dout)
    th = (field - 0.5) * 2.0 * float(amount)
    return Image.fromarray(((signed + th) > 0).astype(np.uint8) * 255, "L")


def _dilate_x(mask, k):
    """只在水平方向膨胀 k 像素。

    这是做「海报体 / fat face」的关键：衬线体加粗通常是整体吹胖，
    横竖一起粗，字腔跟着糊死；只往左右膨胀，就得到粗竖线 + 细横线的
    fat-face 结构，字腔还开着——参考图的字母正是这个骨架。
    """
    if k <= 0:
        return mask
    try:
        import numpy as np
        from scipy.ndimage import grey_dilation
    except ImportError:
        return mask.filter(ImageFilter.MaxFilter(min(k * 2 + 1, 61)))
    a = np.asarray(mask)
    out = grey_dilation(a, size=(1, k * 2 + 1))
    return Image.fromarray(out.astype("uint8"), "L")


def build_word(word, target_w, font_path, squeeze, tracking, weight,
               weight_pct=None, fat_pct=None):
    """单行大写词 → L 蒙版（已压缩、已加粗）。返回 (mask, 实际字号)

    weight_pct 给了就按字号的百分比算加粗量，覆盖 weight 的绝对像素。
    海报的字高动辄六七百像素，固定 3px 的膨胀等于没加——粗细必须跟着字号走。
    """
    size = _fit_size(word, target_w / max(squeeze, 0.2), font_path)
    font = ImageFont.truetype(font_path, size)
    if weight_pct is not None:
        weight = max(0, int(round(size * float(weight_pct))))

    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    gap = int(size * tracking)
    widths, boxes = [], []
    for ch in word:
        b = probe.textbbox((0, 0), ch, font=font)
        widths.append(b[2] - b[0])
        boxes.append(b)
    total_w = sum(widths) + gap * (len(word) - 1)

    asc, desc = font.getmetrics()
    pad = size
    layer = Image.new("L", (total_w + pad * 2 + 4, asc + desc + pad * 2 + 4), 0)
    d = ImageDraw.Draw(layer)

    x = pad
    base_y = pad
    for ch, b, w in zip(word, boxes, widths):
        d.text((x - b[0], base_y), ch, font=font, fill=255)
        x += w + gap

    layer = layer.crop(layer.getbbox())

    # 加粗：先按字号的百分比做横向膨胀（fat face），再叠加整体膨胀
    if fat_pct:
        layer = _dilate_x(layer, max(0, int(round(size * float(fat_pct)))))
    if weight > 0:
        layer = layer.filter(ImageFilter.MaxFilter(int(weight) * 2 + 1))

    # 水平压缩 —— 「压缩体」的密度来源
    nw = max(1, int(layer.width * squeeze))
    layer = layer.resize((nw, layer.height), Image.LANCZOS)
    return layer, size


def draw_tracked(draw, xy, text, font, fill, tracking):
    """宽字距排版（底部关键词行那种疏排小字）。返回总宽。"""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + tracking
    return x - xy[0] - tracking


def paste_rotated_text(base, text, font_path, size, fill, center, angle, anchor="center"):
    """斜着手写标语：先画到透明层，旋转后贴回。anchor: left/center/right"""
    font = ImageFont.truetype(font_path, size)
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    b = probe.textbbox((0, 0), text, font=font)
    pad = size
    tmp = Image.new("RGBA", (b[2] - b[0] + pad * 2, b[3] - b[1] + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    d.text((pad - b[0], pad - b[1]), text, font=font, fill=tuple(fill) + (255,))
    tmp = tmp.rotate(angle, expand=True, resample=Image.BICUBIC)

    if anchor == "right":
        left = int(center[0] - tmp.width)
    elif anchor == "left":
        left = int(center[0])
    else:
        left = int(center[0] - tmp.width / 2)
    top = int(center[1] - tmp.height / 2)
    base.paste(tmp, (left, top), tmp)
    return tmp.size


# ---------------------------------------------------------------- 质感
def _cover_to(im, tw, th, focus=(0.5, 0.5), zoom=1.0):
    """把原图 cover 到指定尺寸，再按 focus(0-1) 决定取哪一段。
    focus=(0.5,0.5) 居中；focus_y 越小越靠上。同一套参数也用于 alpha，永不错位。"""
    w, h = im.size
    s = max(tw / w, th / h) * max(zoom, 0.2)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    big = im.resize((nw, nh), Image.LANCZOS)
    left = -round((nw - tw) * focus[0])
    top = -round((nh - th) * focus[1])
    canvas = Image.new(im.mode, (tw, th))
    canvas.paste(big, (left, top))
    return canvas


def _cover_full(im, W, H, bx, by, bw, bh, focus=(0.5, 0.5), zoom=1.0):
    """按 (bw,bh) 算出的取景，铺到整张画布上。

    字形框之外也得有像素——主体探出字边时贴的就是这些像素。以前只在框内贴一层，
    框外是空的，于是"溢出"永远伸不出去，只在框内改了改颜色。
    变换与 _cover_to 完全一致，同一个 focus/zoom，像素级对齐。"""
    w, h = im.size
    s = max(bw / w, bh / h) * max(zoom, 0.2)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    big = im.resize((nw, nh), Image.LANCZOS)
    left = bx - round((nw - bw) * focus[0])
    top = by - round((nh - bh) * focus[1])
    canvas = Image.new(im.mode, (W, H))
    canvas.paste(big, (left, top))
    return canvas


def _tight_bbox(subject, bottom_frac=0.10, side_frac=0.04, slice_frac=0.12):
    """抠图常把主体脚下的地面、身后的空墙一起算进来，直接用 getbbox() 会把
    字母窗撑成一张「地景照」。

    只从**底边和两侧**往里收：脚下的台子、草地、桌面质量稀薄，收掉；
    顶边不动 —— 耳朵、帽檐、天线这类部件本身就是细的，按质量判会被误切，
    而 alpha 的顶边本来就贴着主体。

    判据：最外一段（占当前边长 slice_frac）装的主体质量不到阈值，就算虚边。"""
    a = subject.getchannel("A")
    try:
        import numpy as np
        m = np.asarray(a, dtype="float32")
    except ImportError:
        return a.getbbox()
    if m.sum() <= 0:
        return a.getbbox()
    h, w = m.shape
    rows, cols = m.sum(axis=1), m.sum(axis=0)
    bb = a.getbbox()
    y0, x0, x1 = bb[1], bb[0], bb[2]
    y1 = bb[3]

    def trim_end(hi, prof, lo, frac):
        while hi - lo > 16:
            k = max(1, int(round((hi - lo) * slice_frac)))
            band = prof[lo:hi].sum()
            if band <= 0:
                break
            if prof[hi - k:hi].sum() / band >= frac:
                break
            hi -= k
        return hi

    def trim_start(lo, prof, hi, frac):
        while hi - lo > 16:
            k = max(1, int(round((hi - lo) * slice_frac)))
            band = prof[lo:hi].sum()
            if band <= 0:
                break
            if prof[lo:lo + k].sum() / band >= frac:
                break
            lo += k
        return lo

    y1 = trim_end(y1, rows, y0, bottom_frac)
    x0 = trim_start(x0, cols, x1, side_frac)
    x1 = trim_end(x1, cols, x0, side_frac)
    if x1 - x0 < 16 or y1 - y0 < 16:
        return bb
    return (x0, y0, x1, y1)


def _ground_row(alpha, min_gap=0.04, thr=0.55):
    """找照片里主体「落地」的那一行：身体到这儿为止，再往下只剩细的部件（爪、尾巴）。

    做法很朴素：逐行数主体宽度，从底边往上走，第一行"够宽"的地方就是地面线。
    参考图就是靠这条线——字的下沿压在地面线上，于是爪子自己垂到字外，
    而身体不会越界。这一条让「字中有画、字外见爪」变成一次对齐，而不是一堆参数。
    没有明显地面线（细部件占比太小）时返回 None，退回原来的居中。
    """
    try:
        import numpy as np
    except ImportError:
        return None
    m = np.asarray(alpha) > 128
    if not m.any():
        return None
    rows = m.sum(axis=1).astype(np.float32)
    ys = np.where(rows > 0)[0]
    if len(ys) < 8:
        return None
    y0, y1 = int(ys.min()), int(ys.max())
    thr = float(thr) * float(rows[ys].max())
    y = y1
    while y > y0 and rows[y] < thr:
        y -= 1
    if (y1 - y) < max(3, int(min_gap * (y1 - y0))):
        return None                      # 底下没有细部件，不用对
    return y


def _fit_subject(im, bb, tw, th, extra=1.0, fill=0.8, max_zoom=2.4):
    """算出让主体「铺满」字母窗的 (zoom, focus)。

    字母窗要的不是整张原图，是照片里的主角。所以先量主体 bbox，再反推缩放：
    - z_in：把主体完整放进窗口需要的倍数（含得住，但四周留背景）；
    - z_cov：让主体盖满窗口的倍数（铺得满，但会切掉边角）；
    - fill 在这两者之间取值 0-1，默认 0.8 —— 主体占满字形、边缘只轻轻切一点。
    extra 是用户手动叠加的 --window-zoom（想更近就 >1）。
    返回的 zoom 与 focus 同时用于照片和主体 alpha，所以两者永不错位。
    """
    bw = max(1.0, float(bb[2] - bb[0]))
    bh = max(1.0, float(bb[3] - bb[1]))
    w, h = im.size
    base = max(tw / w, th / h)                       # zoom=1 时的缩放
    z_in = max(min(tw / (bw * base), th / (bh * base)), 1.0)
    z_cov = max(max(tw / (bw * base), th / (bh * base)), z_in)
    zoom = (z_in ** (1.0 - fill)) * (z_cov ** fill)
    zoom = min(max(zoom * max(extra, 0.2), 0.2), max_zoom)
    s = base * zoom
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    cx = (bb[0] + bb[2]) / 2 * s
    cy = (bb[1] + bb[3]) / 2 * s
    fx = (cx - tw / 2) / (nw - tw) if nw - tw > 1 else 0.5
    fy = (cy - th / 2) / (nh - th) if nh - th > 1 else 0.5
    return zoom, (min(1.0, max(0.0, fx)), min(1.0, max(0.0, fy)))


def _print_treat(im, amount):
    """老印刷做旧：暖光提亮 + 提对比 + 低频斑块 + 轻微去饱和。

    参考图里字母内的照片不是"新拍的"，而是像一版套印偏了的旧画片——亮部发暖、
    暗部抬起来、表面有大小不一的斑。这一层只作用在照片区域，底色保持干净平涂。

    注意别只提亮不提对比：单纯 ×1.16 + lift 会把整块照片推成灰雾，
    猫毛那股暖橙色的劲道全没了，看着像隔了层脏玻璃。
    """
    a = max(0.0, min(1.0, amount))
    if a <= 0:
        return im
    # 旧印片的黑位不会是 0。先把黑位整体抬起来（bp），照片才有「印在纸上」的
    # 感觉；只乘系数 + lift 的话暗部还是黑的，一眼是屏幕里的照片。
    bp = 47 * a
    k = 1.0 + 0.10 * a
    lift = 8 * a
    out = im.point(lambda v: min(255, int(bp + v * (1.0 - bp / 255.0) * k + lift)))
    # 轻 S 形加回层次，然后压高光：旧印刷的亮部是奶白不是纯白，
    # 让它冲过 235 的话，白猫那块会亮过字外的底色，字当场散架。
    c = 1.0 + 0.07 * a
    out = out.point(lambda v: max(0, min(255, int(128 + (v - 128) * c))))
    knee = 235 - 45 * a
    out = out.point(lambda v, k=knee: int(k + (v - k) * 0.55) if v > k else v)
    try:
        import numpy as np
        small = (max(8, im.width // 22), max(8, im.height // 22))
        rnd = Image.effect_noise(small, 48).resize(im.size, Image.BICUBIC)
        rnd = rnd.filter(ImageFilter.GaussianBlur(max(3, im.width * 0.004)))
        n = np.asarray(rnd).astype(np.float32) / 255.0 - 0.5
        arr = np.asarray(out).astype(np.float32)
        arr = arr + n[..., None] * (46.0 * a)
        out = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGB")
    except ImportError:
        pass
    # 极轻去饱和，只压掉"数码鲜艳"那一档；再补一点暖色偏移，像旧纸吃进黄光
    gray = out.convert("L").convert("RGB")
    out = Image.blend(out, gray, 0.08 * a)
    if a > 0:
        # 旧纸是吃进黄光的：红抬、蓝压，中间调再垫一点米色
        r, g, b = out.split()
        r = r.point(lambda v: min(255, int(v + 8 * a)))
        g = g.point(lambda v: min(255, int(v + 2 * a)))
        b = b.point(lambda v: max(0, int(v - 8 * a)))
        out = Image.merge("RGB", (r, g, b))
    return out


def _add_grain(im, amount):
    if amount <= 0:
        return im
    noise = Image.effect_noise(im.size, 30).convert("L")
    n3 = Image.merge("RGB", (noise, noise, noise))
    return Image.blend(im, n3, min(0.18, amount * 0.18))


def _add_vignette(im, strength):
    if strength <= 0:
        return im
    W, H = im.size
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((-W * 0.28, -H * 0.28, W * 1.28, H * 1.28), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(W * 0.10))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(im, Image.blend(im, dark, strength), mask)


def _auto_ink(bg):
    """镂空字用什么颜色压照片。

    深底上直接用底色本身——字就是"从照片带里抠出来的洞"，和版面同色最安分。
    浅底上不能这么干：米白字压在照片上等于没有字，必须换一支同色相的深墨。
    """
    try:
        h = bg.lstrip("#")
        rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    except Exception:
        return bg
    if _lum(rgb) > 0.45:
        return _tone(rgb, 0.13, 1.0)
    return bg


def _auto_text_color(bg):
    """按底色明度自动选米白或深墨，保证小字可读。"""
    try:
        h = bg.lstrip("#")
        rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    except Exception:
        return (242, 232, 213)
    return (242, 232, 213) if _lum(rgb) < 0.55 else (28, 27, 25)


# ---------------------------------------------------------------- 抠图
def _dilate(mask, px):
    """把蒙版向外扩 px 像素（精确距离变换，比 MaxFilter 快且不受核尺寸限制）。"""
    if px <= 0:
        return mask
    try:
        import numpy as np
        from scipy.ndimage import distance_transform_edt
    except ImportError:
        return mask.filter(ImageFilter.MaxFilter(min(int(px) * 2 + 1, 61)))
    m = np.asarray(mask) > 128
    dist = distance_transform_edt(~m)
    return Image.fromarray(((dist <= px) * 255).astype("uint8"), "L")


def _profile_zone(sa, win, direction, depth, min_prot=20, max_cover=0.34,
                  max_run=0.18, dbg=""):
    """在某个方向上，主体能越出字形多远 —— 只放行"比整条边更凸出"的部件。

    石台、桌面、躺着的身体，边缘是一条直的水平线：渗出去的深度在宽度方向上是平的，
    减去中位数就抹平了。一只爪、一只耳朵、一个鞋头是局部凸起，减完还剩一截。
    这一条就是"伸出来的是部件还是整条边"的机器判据，比按接触面宽度一刀切准得多。

    min_prot 是"凸出多少像素才算部件"，必须按字高的绝对比例给（3% 上下），
    不能用 depth 的倍数——depth 是允许伸出的半径，可以给到 0.4 字高，
    乘出来的门槛就成了 150px，天底下没有哪只爪子凸 150px，判定永远返回 None。
    """
    try:
        import numpy as np
    except ImportError:
        return None
    m = np.asarray(sa) > 128
    w = np.asarray(win) > 128
    if not m.any() or not w.any():
        return None

    # 统一成"往下溢出"来处理，其余方向靠翻转/转置
    if direction == "down":
        M, Wm, undo = m, w, (lambda z: z)
    elif direction == "up":
        M, Wm, undo = m[::-1, :], w[::-1, :], (lambda z: z[::-1, :])
    elif direction == "left":
        M, Wm, undo = m.T[:, ::-1], w.T[:, ::-1], (lambda z: z[:, ::-1].T)
    elif direction == "right":
        M, Wm, undo = m.T, w.T, (lambda z: z.T)
    else:
        return None

    Hm, Wd = M.shape
    rows = np.arange(Hm)[:, None]
    # 基准线用字形外接框的那条边，不是"每列字形的最低点"。
    # 用每列最低点会被字母自己的缺口骗到：A 的底部中间没有笔画，
    # 那一列的"字形底"落在横杠上，主体自然比它低 500px，判定当场失真。
    ref = int(np.where(Wm.any(axis=1))[0].max())
    ext = np.where(M, rows, -1).max(axis=0)          # 主体每列最低行
    has_win = Wm.any(axis=0)
    ok = (ext >= 0) & has_win
    if not ok.any():
        return None
    d = np.where(ok, ext - ref, -10 ** 6)
    pos = d > 0
    if not pos.any():
        return None
    base = float(np.median(d[pos]))
    gate = pos & ((d - base) > max(4, min_prot))
    if dbg:
        dd = d[pos]
        print(f"    [{dbg}] 基准行 {ref}  有效列 {int(ok.sum())}  溢出列 {int(pos.sum())}  "
              f"中位 {base:.0f}  p90 {np.percentile(dd, 90):.0f}  max {dd.max():.0f}  "
              f"门槛 {max(4, min_prot):.0f}  → 放行 {int(gate.sum())}"
              + ("（列占比超限，撤回）"
                 if gate.any() and gate.sum() > max_cover * max(1, int(ok.sum())) else ""))
    if not gate.any():
        return None
    # 部件是窄的。放行的列占到字形宽度三分之一还多，说明贴着字的是一整条边
    # （石台、草莓堆、毯子），不是"伸出来的东西"，这个方向直接放弃。
    if gate.sum() > max_cover * max(1, int(ok.sum())):
        return None

    # 再把连续段过长的一并砍掉。逐列判定能认出"比边更凸"，但一只趴着的猫整条
    # 肚皮也会微微比边低一点，连起来就是一条几百像素的横带——那仍然是边。
    # 真正的部件（一只爪、一只耳朵）是窄而深的：段短，而且比周围深出好几倍。
    runs = []
    i = 0
    idx = np.where(gate)[0]
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and idx[j + 1] == idx[j] + 1:
            j += 1
        runs.append((int(idx[i]), int(idx[j])))
        i = j + 1
    deep = base + 1.30 * max(4, min_prot)
    keep_runs = []
    for s, e in runs:
        ln = e - s + 1
        if ln > max(3, int(max_run * max(1, int(ok.sum())))):
            continue                      # 太长，是边不是部件
        if float(np.mean(d[s:e + 1])) < deep:
            continue                      # 不够深，是整体让位不是探出
        keep_runs.append((s, e))
    if dbg:
        print(f"    [{dbg}] 段 [{', '.join(f'{s}-{e}' for s, e in runs)}] "
              f"→ 保留 [{', '.join(f'{s}-{e}' for s, e in keep_runs)}]")
    if not keep_runs:
        return None

    z = np.zeros((Hm, Wd), np.uint8)
    for s, e in keep_runs:
        ln = e - s + 1
        # 只有一两列的毛边（飘起来的一根毛）不做：贴出去就是一根悬空的细丝。
        if ln < max(4, int(0.006 * Wd)):
            continue
        for xx in range(s, e + 1):
            # 收成一个「叶瓣」：段两端降到 0，和字形边贴回去，中间最深。
            # 少了这一步，放行段的外沿就是一条水平直线——渗出来的是方角方边的方块，
            # 看着像贴纸没剪干净，不像爪子/耳朵探出来。taper 让轮廓自己带弧度。
            taper = math.sin(math.pi * (xx - s + 0.5) / ln) ** 0.55
            reach = min(int(d[xx]), max(1, int(round(depth * taper))))
            y0, y1 = ref, int(min(Hm - 1, ref + reach))
            if y1 > y0:
                z[y0:y1 + 1, xx] = 255

    zi = Image.fromarray(np.ascontiguousarray(undo(z)), "L")
    # 1px 级柔边：硬边在照片上会留下一道刀切线
    return zi.filter(ImageFilter.GaussianBlur(1.2))


def _leak_ratio(mask, anchor):
    """渗到字形之外的面积 / 字形面积。太大说明主体是一整片（草莓堆、毛毯），
    放出去就是整块照片，字彻底读不出来。"""
    try:
        import numpy as np
    except ImportError:
        return 0.0
    m = np.asarray(mask) > 128
    a = np.asarray(anchor) > 128
    base = max(1, int(a.sum()))
    return float((m & ~a).sum()) / base


def _outer_fringe(sa, region, depth, dirs=("down", "up"), htaper=0.12, solid=False):
    """字母外缘的「淡出补图」：照片从单词外接框边上渗出去一点，然后逐渐化掉。

    为什么不是"再放行几个部件"：参考图里字外露的不是零件，是**整幅画继续往下/往右延**——
    橘猫前爪垂在字下、白猫的毛越过字右缘、字底还有一条台面。这些是宽的，逐列凸出判定
    （要求又窄又深）永远判不出来，硬放行就变成一条生硬的照片横带。

    做法是给一个只在**外接框之外**存在的软边遮罩：贴着框边不透明，越远越透，depth 像素外归零。
    框内的字缝、字腔一概不碰，所以字还是字；框外自然淡出，所以不像贴了一条照片。
    """
    try:
        import numpy as np
    except ImportError:
        return None
    r = np.asarray(region) > 128
    if not r.any():
        return None
    H, W = r.shape
    # solid=True：用整张照片（不乘主体 alpha）。抠图的边是算法给的，露到字外就是一块
    # 剪坏了的碎片；而照片本身的延续（台面、墙、毛）怎么看都是"同一张画"，才像画面完整。
    m = np.ones_like(r) if solid else (np.asarray(sa) > 128)
    ys, xs = np.where(r)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    d = max(2.0, float(depth))
    yy = np.arange(H, dtype=np.float32)[:, None]
    xx = np.arange(W, dtype=np.float32)[None, :]
    dx = np.maximum(np.maximum(x0 - xx, xx - x1), 0.0)
    dy = np.maximum(np.maximum(y0 - yy, yy - y1), 0.0)
    dist = np.sqrt(dx * dx + dy * dy)
    # 只做上/下（默认）：左右两侧一旦放开，画面左右边缘会各出一条竖着的照片毛边，
    # 像图没对齐漏出来的——那不是"画面完整"，是穿帮。
    if "left" not in dirs:
        dx = np.where(xx < x0, 0.0, dx)
    if "right" not in dirs:
        dx = np.where(xx > x1, 0.0, dx)
    if "up" not in dirs:
        dy = np.where(yy < y0, 0.0, dy)
    if "down" not in dirs:
        dy = np.where(yy > y1, 0.0, dy)
    dist = np.sqrt(dx * dx + dy * dy)
    # 框内一律为 0：只补「框外」那一圈。框里交给字形和字缝，补图一进去就把字糊了。
    # 边缘要「脆」：只有最后 25% 的距离做过渡，中段全是实心。整段都做渐变的话，
    # 字外就是一圈半透明的模糊亮晕——那不是照片延续，是发光。
    soft = max(3.0, d * 0.45)
    a = np.where(dist > 0.5, np.clip((d - dist) / soft, 0.0, 1.0) ** 0.75, 0.0)
    # 横向两端收口：不收的话，照片带会在字的两端齐刷刷断掉，像贴纸没剪干净
    if htaper > 0:
        tw = max(1.0, (x1 - x0) * htaper)
        edge = np.clip(np.minimum(xx - x0, x1 - xx) / tw + 0.35, 0.0, 1.0)
        a = a * edge
    a = a * m
    if not (a > 0.02).any():
        return None
    # 抠图的边本身是毛的（尤其是腿和身体之间那道缝），直接当轮廓用就成了狗牙。
    # 这里按深度给 8px 量级的柔化，边缘还看得出形状，但不毛。
    return Image.fromarray((a * 255).astype("uint8"), "L").filter(
        ImageFilter.GaussianBlur(max(2.5, d * 0.12)))


def _keep_touching(mask, anchor, grow=4):
    """只留和字形相连的块。

    主体和字形之间偶尔会隔着一层透明（一撮飘起来的毛），渗出去就成了悬空的亮斑，
    读者只会觉得画面脏了。和字形接不上的块一律丢掉。"""
    try:
        import numpy as np
        from scipy.ndimage import label, binary_dilation
    except ImportError:
        return mask
    m = np.asarray(mask) > 128
    a = np.asarray(anchor) > 128
    lab, n = label(m)
    if n == 0:
        return mask
    ring = binary_dilation(a, iterations=grow) & ~a
    touch = np.unique(lab[ring & m])
    touch = touch[touch > 0]
    if touch.size == 0:
        return mask
    keep = np.isin(lab, touch)
    return Image.fromarray((keep * 255).astype("uint8"), "L")


def _open_negative(glyph):
    """字母之外、并且与画面外侧连通的区域 —— 也就是「字缝 + 四周留白」。

    被字母整个包住的小孔（A 的三角、C 的碗、S 的两个口）不算：那是字腔，
    填进去字就不成形了。参考图里猫身能横过字缝，但 A 的三角始终是深的。"""
    try:
        import numpy as np
        from scipy.ndimage import label
    except ImportError:
        return None
    m = np.asarray(glyph) > 128
    lab, n = label(~m)
    corner = lab[0, 0]
    if corner == 0 or n <= 1:
        return None
    return Image.fromarray(((lab == corner) * 255).astype("uint8"), "L")


def draw_paw(d, center, size, color):
    """一枚小爪印：一个掌垫 + 四颗脚趾。"""
    cx, cy = center
    s = float(size)
    d.ellipse((cx - s * 0.50, cy - s * 0.02, cx + s * 0.50, cy + s * 0.60), fill=color)
    for dx, dy, r in ((-0.60, -0.30, 0.25), (-0.21, -0.58, 0.24),
                      (0.21, -0.58, 0.24), (0.60, -0.30, 0.23)):
        tx, ty, rr = cx + s * dx, cy + s * dy, s * r
        d.ellipse((tx - rr, ty - rr, tx + rr, ty + rr), fill=color)


def draw_sun(d, center, r, color, width):
    """手绘小太阳：一个圈 + 八道短射线。"""
    import math
    cx, cy = center
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width)
    for i in range(8):
        th = i * math.pi / 4 + math.pi / 11
        c, sn = math.cos(th), math.sin(th)
        d.line((cx + c * r * 1.42, cy + sn * r * 1.42,
                cx + c * r * 2.30, cy + sn * r * 2.30), fill=color, width=width)


def _spill_zone(W, H, x, top_y, bw, bh, direction, spill):
    """溢出只在指定方向的窄带里发生，窗口本身不算溢出。"""
    box = None
    d = int(bh * spill * 1.7)
    if direction == "down":
        # 下界收在底部小字上方，免得伸出的主体把小字糊掉
        box = (0, top_y + bh - int(bh * 0.12), W,
               min(H, top_y + bh + d))
    elif direction == "up":
        box = (0, max(0, top_y - d), W, top_y + int(bh * 0.12))
    elif direction == "left":
        box = (0, 0, x + int(bw * 0.12), H)
    elif direction == "right":
        box = (x + bw - int(bw * 0.12), 0, W, H)
    elif direction == "sides":
        box = None  # 交给下面的双侧处理
    if direction == "sides":
        zone = Image.new("L", (W, H), 0)
        dg = ImageDraw.Draw(zone)
        dg.rectangle((0, 0, x + int(bw * 0.12), H), fill=255)
        dg.rectangle((x + bw - int(bw * 0.12), 0, W, H), fill=255)
        return zone
    if direction == "all" or box is None:
        return Image.new("L", (W, H), 255)
    zone = Image.new("L", (W, H), 0)
    ImageDraw.Draw(zone).rectangle(box, fill=255)
    return zone


def _segment(im):
    """抠出主体 → RGBA。rembg 不可用时返回 (None, 原因)，调用方自动退回压边模式。"""
    try:
        from rembg import remove, new_session
    except ImportError:
        return None, "rembg 未安装"
    try:
        session = new_session("u2net")
        out = remove(im, session=session)
        return out.convert("RGBA"), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- poster
def cmd_poster(a):
    src = Path(a.image)
    if not src.exists():
        sys.exit(f"[x] 文件不存在：{src}")

    im = Image.open(src)
    im = ImageOps.exif_transpose(im).convert("RGB")

    _sz = a.size or ("1440x1000" if a.mode == "glyph" else "1152x1536")
    W, H = (int(x) for x in _sz.lower().split("x"))
    bg = a.bg or "#2A211C"

    # 逐模式默认值。glyph 是一整幅字母海报：字顶天立地、左右出血、几乎没有字距，
    # 上方不另压照片横条——参考图的画面上半是字母本身，不是一条照片带。
    band_mode = (a.mode == "band")
    glyph_mode = (a.mode == "glyph")
    font_path = pick_font(a.font, glyph=glyph_mode)
    # 比例全部按参考图实测（529×368 成片逐行量出来的，不是目测）：
    # 字母带 y 0.195-0.800（高 0.605H）、左右 0.05-0.98（宽 0.93W），
    # 字缝细到 0.019W，字号粗到笔画宽 0.067H。
    # 早期把 tracking 给到 0.09 想"留出字缝"，结果字变窄、缝变宽，整幅照片覆盖率
    # 只有 33%（参考 44%），一眼就空——字缝要靠字够宽自己挤出来，不能靠加字距。
    _def = dict(word_width=0.960, squeeze=0.550, tracking=0.030, height_ratio=0.573,
                max_bleed=0.98, letter_gap=0.209, bottom_pad=0.165) if glyph_mode else \
           dict(word_width=0.96, squeeze=0.72, tracking=-0.02, height_ratio=0.52,
                max_bleed=1.12, letter_gap=0.006, bottom_pad=0.10)
    word_width = a.word_width if a.word_width is not None else _def["word_width"]
    squeeze = a.squeeze if a.squeeze is not None else _def["squeeze"]
    tracking = a.tracking if a.tracking is not None else _def["tracking"]
    height_ratio = a.height_ratio if a.height_ratio is not None else _def["height_ratio"]
    max_bleed = a.max_bleed if a.max_bleed is not None else _def["max_bleed"]
    letter_gap = a.letter_gap if a.letter_gap is not None else _def["letter_gap"]
    bottom_pad = a.bottom_pad if a.bottom_pad is not None else _def["bottom_pad"]
    tag_size = a.tag_size if a.tag_size is not None else (0.046 if glyph_mode else 0.040)
    # 字重：glyph 要"粗体大块"，按字号比例膨胀；band/window 保留像素级微调
    weight = a.weight if a.weight is not None else (0 if glyph_mode else 3)
    weight_pct = a.weight_pct if a.weight_pct is not None else (0.0 if glyph_mode else None)
    fat_pct = a.fat_x if a.fat_x is not None else (0.030 if glyph_mode else None)

    # ① 先排版，拿到字母外接框（照片对位需要知道窗口在哪）
    word = a.word.upper()
    split = a.split if a.split is not None else (0.0 if glyph_mode else 0.5)
    split_y = round(H * split)
    lower_h = H - split_y

    # 有手写标语时，字顶必须让开（标语高度 + 照片压边量），否则标语会骑在照片边上
    gap = letter_gap
    if a.tag:
        # 标语高度是相对画布宽的，gap 是相对画布高的，别直接相加。
        # band 还要多让一个 bite（照片压过字顶的量）；glyph 是一整幅海报，
        # 标语压在字母上沿，只让一点点，让多了字母就被压矮。
        if glyph_mode:
            gap = max(gap, tag_size * 0.55)
        else:
            gap = max(gap, tag_size * 1.05 + a.bite)

    fmask, size = build_word(word, W * word_width, font_path, squeeze, tracking, weight, weight_pct, fat_pct)
    need_h = lower_h * height_ratio
    if height_ratio > 0 and fmask.height < need_h:
        boost = need_h / fmask.height
        # 出血上限：宽度最多溢出画布 15%，再多就切掉字母了
        boost = min(boost, (W * max_bleed) / fmask.width)
        if boost > 1.001:
            fmask, size = build_word(word, W * word_width * boost, font_path,
                                     squeeze, tracking, weight, weight_pct, fat_pct)

    x = (W - fmask.width) // 2
    top_y = round(split_y + H * gap)

    # 标语 + 字高 + 底部余量 放不下时，自动把字缩回去（先保版式，再保字号）
    avail = H - round(H * bottom_pad) - round(split_y + H * gap)
    if fmask.height > avail > 0:
        fmask, size = build_word(word, W * word_width * (avail / fmask.height),
                                 font_path, squeeze, tracking, weight, weight_pct, fat_pct)
        x = (W - fmask.width) // 2

    limit = H - round(H * bottom_pad) - fmask.height
    top_y = min(top_y, limit)
    top_y = max(top_y, split_y)

    # ② 抠主体（原图尺寸），只为拿到它的位置，用来决定照片怎么对位
    subject_src = None
    cut_msg = None
    if a.cut:
        subject_src, err = _segment(im)
        if subject_src is None:
            cut_msg = f"抠图未启用（{err}），已退回照片压边模式"

    # ③ 照片取景
    #    split=0（glyph）时没有顶部横条，photo_h 归零，⑥ 那一步整段跳过。
    photo_h = round(H * (split + a.bite)) if split > 0.01 else 0
    photo_h = max(0, min(photo_h, H))
    photo_top = _cover_to(im, W, max(1, photo_h), (0.5, 0.5)) if photo_h else None

    box_w, box_h = fmask.width, fmask.height
    # 各模式对「满窗」的诉求不一样：带子是横长条，主体整只读得出来最重要；
    # 字形框更接近正方形，可以推得更近。
    fill = a.window_fill if a.window_fill is not None else (0.75 if band_mode else 0.72)
    # 主体必须比字形框大一圈，否则它的边就是字的边，"伸出来"无从谈起。
    subject_out = a.subject_out if a.subject_out is not None else (1.16 if glyph_mode else 1.0)
    if glyph_mode:
        fill = fill * subject_out
    zoom_w, focus_w = a.window_zoom, (0.5, 0.5)
    spill = a.spill if a.spill is not None else (0.14 if glyph_mode else 0.42)
    # glyph 默认只往上、往下探：左右两侧一旦放行，主体会顺着画布边缘糊出一大块亮斑，
    # 那就不是"伸出来的部件"而是漏光。
    spill_dir = a.spill_dir or ("vertical" if glyph_mode else "down")
    distress = a.distress if a.distress is not None else (0.75 if glyph_mode else 0.0)
    gutter_fill = a.gutter_fill if a.gutter_fill is not None else (0.15 if glyph_mode else 0.0)
    # 字外补图：字母外面也露出一点主体，读者才看得出「两只猫」而不是几个字块
    extra = a.extra if a.extra is not None else (0.07 if glyph_mode else 0.0)
    bb = None
    bb_tight = None
    if subject_src is not None:
        bb = subject_src.getchannel("A").getbbox()
        bb_tight = _tight_bbox(subject_src) if bb else None
        if bb:
            if a.fit_subject:
                # 按主体大小反推缩放：窗里必须看到主体，不是看到它脚下的地面
                zoom_w, focus_w = _fit_subject(im, bb_tight or bb, box_w, box_h,
                                               extra=a.window_zoom, fill=fill)
            # 主体占满整幅（草莓堆、毯子、风景这类）没有「部件」可伸，
            # 强行溢出只会把整个面板铺成一块照片，字彻底读不出来。
            # 这一条对 glyph 同样成立：逐列凸出判定挡不住"每一列都凸一点"的铺满型主体。
            if (bb[3] - bb[1]) / im.height > 0.8:
                spill = 0.0

    # 照片带模式下照片铺的是「整条横带」（画布宽 × 字高），对位要按带子重算一次，
    # 否则按字形框算出来的取景装进更宽的带子里，主体会偏到一边。
    band_w, band_h = W, box_h
    zoom_b, focus_b = zoom_w, focus_w
    if band_mode:
        if subject_src is not None and bb_tight and a.fit_subject:
            zoom_b, focus_b = _fit_subject(im, bb_tight, band_w, band_h,
                                           extra=a.window_zoom, fill=fill)
        else:
            zoom_b, focus_b = a.window_zoom, (0.5, 0.5)

    # 地面线对位：把照片里「身体落地」的那一行压到字的基线上。
    # 这样字里是身体、字外自然垂着一只爪——参考图的立体感就是这么来的，
    # 不是靠把溢出半径调大（调大只会让身体整片漏出去）。
    if glyph_mode and a.ground_align and subject_src is not None:
        _g = _ground_row(subject_src.getchannel("A"))
        if _g is not None:
            _s = max(box_w / im.width, box_h / im.height) * max(zoom_w, 0.2)
            _nh = max(1, round(im.height * _s))
            if _nh - box_h > 1:
                _fy = (_g * _s - box_h) / (_nh - box_h)
                focus_w = (focus_w[0], min(1.0, max(0.0, _fy)))

    photo_win = _cover_to(im, box_w, box_h, focus_w, zoom_w)
    photo_full = _cover_full(im, W, H, x, top_y, box_w, box_h, focus_w, zoom_w)
    photo_band = _cover_to(im, band_w, band_h, focus_b, zoom_b)

    # 字形边缘做旧。参考图是丝网/凸版印的，字边是毛的：有缺墨、有溢墨。
    # 干净的矢量边一眼就露是现代软件排的，做旧要作用在「字的轮廓」上，不只是照片。
    if glyph_mode and distress > 0:
        fmask = _wear_edge(fmask, max(2, int(box_h * 0.007 * distress)))

    canvas = Image.new("RGB", (W, H), bg)
    ink = a.ink or _auto_ink(bg)
    win = Image.new("L", (W, H), 0)
    win.paste(fmask, (x, top_y))
    photo_zone = win          # 需要做旧的照片区域（字母 + 渗出去的那点）

    # ④ 照片层
    if band_mode:
        # 照片带：一条横贯画面的连续照片。字间空隙、字母空腔里都是它，画面才连得住。
        canvas.paste(photo_band, (0, top_y))
        region = Image.new("L", (W, H), 0)
        ImageDraw.Draw(region).rectangle((0, top_y, W, top_y + band_h), fill=255)
        zx, zw, zh = 0, band_w, band_h
    else:
        win_layer = Image.new("RGB", (W, H), bg)
        win_layer.paste(photo_win, (x, top_y))
        canvas.paste(win_layer, (0, 0), win)
        region = win
        zx, zw, zh = x, box_w, box_h

    if os.environ.get("LETTERKIT_DEBUG"):
        win.save(os.path.splitext(a.out)[0] + "_win.png")
        fmask.save(os.path.splitext(a.out)[0] + "_fmask.png")
        if band_mode:
            photo_band.save(os.path.splitext(a.out)[0] + "_band.png")
        else:
            win_layer.save(os.path.splitext(a.out)[0] + "_layer.png")

    # ⑤ 窗框（默认关，且只在字母窗模式里有意义）：字形外扩一圈细线
    if a.rim > 0 and not band_mode:
        grown = win.filter(ImageFilter.MaxFilter(int(a.rim) * 2 + 1))
        ring = ImageChops.multiply(grown, win.point(lambda v: 255 - v))
        canvas.paste(Image.new("RGB", (W, H), a.rim_color), (0, 0), ring)

    # ⑥ 照片压过字母：上半照片贴回顶部一横条（glyph 无此层）
    if photo_top is not None:
        canvas.paste(photo_top, (0, 0))

    # ⑥b 立体穿插：主体 → 接触投影 → 压在最上层
    #     主体在窗/带内与照片重合（看不出差别），在窗/带外才"伸出来"，于是有了前后层次。
    if a.cut and subject_src is not None:
        # 主体 alpha 走与照片完全相同的取景，保证像素级对齐
        if band_mode:
            sa_small = _cover_to(subject_src.getchannel("A"), band_w, band_h, focus_b, zoom_b)
            sa = Image.new("L", (W, H), 0)
            sa.paste(sa_small, (0, top_y))
        else:
            # 整张画布的 alpha，框外也有值：否则溢出层没有数据可贴
            sa = _cover_full(subject_src, W, H, x, top_y, box_w, box_h,
                             focus_w, zoom_w).getchannel("A")
        bbox = sa.getbbox()
        if bbox:
            if glyph_mode:
                # 字形模式：字母里本来就有照片，主体只负责两件事——
                # ① 把字与字之间的细缝接上（一点小晕边）；
                # ② 在"比整条边更凸出"的地方伸到字外（爪、耳、鞋头），做出前后层次。
                reach = _dilate(region, max(2, int(box_h * spill)))
                # 晕边只留 2px 做抗锯齿，不要一圈"光"。给到字高的 3% 时，
                # 它会顺着细缝钻进字母的空腔，把 C 的开口糊住，还在字顶外留一块孤立亮斑。
                zone = _dilate(region, 2)
                if spill > 0.01:
                    _dirs = {"all": ["down", "up", "left", "right"],
                             "vertical": ["down", "up"],
                             "sides": ["left", "right"]}.get(spill_dir, [spill_dir])
                    # 凸出门槛按字高给：爪子、耳朵、鞋头的凸出量大约是字高的 3% 上下
                    _prot = max(6, int(box_h * 0.030))
                    for dd in _dirs:
                        z = _profile_zone(sa, region, dd, int(box_h * spill),
                                          min_prot=_prot, max_cover=0.42, max_run=0.26,
                                          dbg=f"{dd}" if os.environ.get("LETTERKIT_DEBUG") else "")
                        if z is not None:
                            zone = ImageChops.lighter(zone, z)
                zone = ImageChops.lighter(zone, region)
                reach = ImageChops.multiply(reach, zone)
                sa_limited = ImageChops.multiply(sa, reach)
                # 字缝贯通：参考图里猫身与爪子是横过字缝的，字缝只在上半段还留着。
                # 这里只放开与画面外侧相连的那部分负形（字缝），A 的三角、C 的碗这类
                # 被字母包住的字腔一概不动——填了字就不成形。
                if gutter_fill > 0:
                    cut_y = int(top_y + box_h * (1.0 - gutter_fill))
                    gz = Image.new("L", (W, H), 0)
                    ImageDraw.Draw(gz).rectangle(
                        (max(0, x), cut_y, min(W, x + box_w), min(H, top_y + box_h)), fill=255)
                    neg = _open_negative(region)
                    if neg is not None:
                        gz = ImageChops.multiply(gz, neg)
                        sa_limited = ImageChops.lighter(sa_limited,
                                                        ImageChops.multiply(sa, gz))
                photo_zone = ImageChops.lighter(photo_zone, sa_limited)
                if spill > 0.01:
                    sa_limited = _keep_touching(sa_limited, region)
                    # 兜底：渗出的总面积还是大得离谱，就整条撤回
                    if _leak_ratio(sa_limited, region) > 1.1:
                        sa_limited = ImageChops.multiply(sa, region)
                        spill = 0.0
                spill_note = (f"{spill_dir} 逐列凸出判定" if spill > 0.01 else "关")
                if extra > 0:
                    spill_note += f" + 字外补图 {extra:.2f} 字高"
            else:
                # 溢出区：限定方向，否则主体会填满整块画布
                reach = _dilate(region, int(box_h * spill))
                zone = _spill_zone(W, H, zx, top_y, zw, zh, spill_dir, spill)
                # 窗口范围内强制满不透明：否则软边会把底色混进去，糊成一片雾
                zone = ImageChops.lighter(zone, region)
                reach = ImageChops.multiply(reach, zone)
                sa_limited = ImageChops.multiply(sa, reach)
                # 溢出宽度体检：躺着的身体、整片毛毯这类，紧贴窗口的是一整条边，
                # 溢出来就是一根横贯画面的照片带 —— 那不是"探出来的部件"，收回去。
                lim = sa_limited.getbbox()
                if lim and spill > 0.01:
                    wide = (lim[2] - lim[0]) / max(1.0, zw)
                    if wide > 0.72 and spill_dir in ("down", "up", "sides", "all"):
                        sa_limited = ImageChops.multiply(sa, region)
                        spill = 0.0
                spill_note = spill_dir
            if a.shadow > 0 and spill > 0.01:
                grow = sa_limited.filter(ImageFilter.MaxFilter(9))
                soft = grow.filter(ImageFilter.GaussianBlur(max(6, H * 0.018)))
                shifted = ImageChops.offset(soft, int(W * 0.006), int(H * 0.010))
                # 投影只留在窗口之外，窗口内的部分交给照片自己
                outside = ImageChops.multiply(shifted, region.point(lambda v: 255 - v))
                outside = outside.point(lambda v: int(v * a.shadow))
                canvas.paste(Image.new("RGB", (W, H), a.shadow_color), (0, 0), outside)
            # 字外补图：照片从单词外缘渗出去一点再化掉，读者才看得出是一整幅画。
            # 必须放在投影之后——放前面的话投影会把补图当成"溢出主体"，
            # 在字下压出一条黑带，看起来像照片断了一截。
            if extra > 0:
                # 只做下方：往上补会在字的顶上留一条细照片线，像套印没对准；
                # 往上露的该是耳朵这种「部件」，交给上面的逐列判定去做。
                _fr_dirs = {"all": ("down", "up", "left", "right"),
                            "vertical": ("down",),
                            "sides": ("left", "right")}.get(spill_dir, (spill_dir,))
                fr = _outer_fringe(sa, region, int(box_h * extra), _fr_dirs)
                if fr is not None:
                    sa_limited = ImageChops.lighter(sa_limited, fr)
                    photo_zone = ImageChops.lighter(photo_zone, fr)
            if band_mode:
                canvas.paste(photo_band, (0, top_y),
                             sa_limited.crop((0, top_y, W, top_y + band_h)))
            else:
                # 用整幅铺开的照片作像素源，主体才能在字外真的露出影像
                canvas.paste(photo_full, (0, 0), sa_limited)
            cut_msg = (f"主体已抠出，溢出 {spill_note}，半径 {spill:.2f}，"
                       f"对位 zoom={zoom_w:.2f} focus=({focus_w[0]:.2f},{focus_w[1]:.2f}) 满窗={fill:.2f}")
    elif a.cut and subject_src is None and cut_msg is None:
        cut_msg = "抠图未启用，已退回照片压边模式"

    # ⑥c 词压在照片带上。两种做法：
    #     key=dark  → 字是深色（veil=1 实心墨块，调低则字内仍透出压暗的照片）；
    #     key=light → 字保持照片原亮度，把字**之外**的照片压暗，字里画面最完整、字间照样是照片。
    if band_mode and a.key == "light":
        keep = 1.0 - (a.veil if a.veil is not None else 0.62)
        dim = (canvas.point(lambda v: max(0, min(255, int(v * keep + 18))))).crop(
            (0, top_y, W, top_y + band_h))
        band_mask = Image.new("L", (W, band_h), 255)
        hole = ImageChops.multiply(band_mask, win.crop((0, top_y, W, top_y + band_h)).point(lambda v: 255 - v))
        canvas.paste(dim, (0, top_y), hole)
    elif band_mode:
        veil = a.veil if a.veil is not None else 0.55
        if veil >= 0.999:
            letter_img = Image.new("RGB", (W, H), ink)
        else:
            keep = 1.0 - veil
            # 单纯乘 keep 会出问题：照片里的高光（草莓的籽、猫的白毛）乘完仍然很亮，
            # 比旁边的字间空隙还亮，字的轮廓当场散架。所以压暗之后再软限幅，
            # 让字内最亮也到不了字间的亮度——画面留着，字形立住。
            ceil = 96.0
            try:
                if band_mode:
                    bm = photo_band.convert("L").resize((1, 1), Image.BOX).getpixel((0, 0))
                    ceil = max(52.0, min(104.0, bm * 0.62))
            except Exception:
                pass

            def _soft(v, _c=ceil, _k=keep):
                t = v * _k
                return int(_c * (1.0 - math.exp(-t / _c)))

            # 只压明度，色相和饱和度留着：猫的橙毛、石头、阴影在同一个暗度下
            # 靠颜色还分得开，眼睛才认得出「字里有画面」。整幅乘系数的做法把颜色
            # 一起压没了，字就成一块匀的深色，和实心墨块没区别。
            # 压完再把带内的明暗关系拉回来一点，纹理才看得见；上限由 ceil 封死，
            # 字内最亮也亮不过字间，轮廓不会散。
            _h, _s, _v = canvas.convert("HSV").split()
            _v = _v.point(_soft)
            _s = _s.point(lambda x: min(255, int(x * 1.50)))
            dark = Image.merge("HSV", (_h, _s, _v)).convert("RGB")
            _bm = photo_band.convert("L").resize((1, 1), Image.BOX).getpixel((0, 0))
            _mid = ceil * (1.0 - math.exp(-_bm * keep / ceil))
            dark = dark.point(lambda x, _m=_mid: max(0, min(255, int(_m + (x - _m) * 1.85))))
            if isinstance(ink, str) and ink.startswith("#"):
                ink_rgb = tuple(int(ink.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            else:
                ink_rgb = (40, 34, 28)
            letter_img = Image.blend(dark, Image.new("RGB", (W, H), ink_rgb), veil * 0.32)
        canvas.paste(letter_img, (0, 0), win)

    # ⑥d 老印刷做旧：只作用在照片上（字母里 + 探出来的部件），底色保持平涂
    if distress > 0 and not band_mode:
        canvas.paste(_print_treat(canvas, distress), (0, 0), photo_zone)

    # ⑦ 装饰一：底部关键词行（宽字距疏排）
    rule_font_path = _first(SANS_FONTS)
    txt_col = a.rule_color or _auto_text_color(bg)
    if rule_font_path and (a.rule_left or a.rule_right):
        rs = max(11, int(W * a.rule_size))
        rf = ImageFont.truetype(rule_font_path, rs)
        tr = max(1.5, rs * 0.22)
        d = ImageDraw.Draw(canvas)
        by = H - int(H * bottom_pad * 0.55) - rs
        if a.rule_left:
            draw_tracked(d, (int(W * 0.045), by), a.rule_left, rf, txt_col, tr)
        if a.rule_right:
            tw = sum(rf.getlength(c) for c in a.rule_right) + tr * (len(a.rule_right) - 1)
            draw_tracked(d, (int(W * 0.955 - tw), by), a.rule_right, rf, txt_col, tr)

    # ⑧ 装饰二：手写标语（默认落在字顶与分界线之间的空档里）
    if a.tag:
        sp = _first(SCRIPT_FONTS)
        if sp:
            ts = max(18, int(W * tag_size))
            tag_col = a.tag_color or txt_col
            # glyph 没有分界线，标语贴着画布上沿、被裁掉下缘一点点（参考图就是这样）；
            # band 落在照片顶与分界线的空档正中。
            if glyph_mode:
                # 参考图标语中心落在字顶往上三分之一处（top_y=0.197H 时约 0.135H）
                band_y = max(int(H * 0.055), int(top_y * 0.78))
            else:
                band_y = int((max(split_y, photo_h) + top_y) / 2)
            if a.tag_pos == "tr":
                paste_rotated_text(canvas, a.tag, sp, ts, tag_col,
                                   (int(W * 0.930), band_y), a.tag_rotate, "right")
            elif a.tag_pos == "tl":
                paste_rotated_text(canvas, a.tag, sp, ts, tag_col,
                                   (int(W * 0.070), band_y), a.tag_rotate, "left")
            else:  # br 放到字母下沿外侧
                paste_rotated_text(canvas, a.tag, sp, ts, tag_col,
                                   (int(W * 0.930), int(min(H - H * 0.09, top_y + fmask.height + H * 0.045))),
                                   a.tag_rotate, "right")
            dd = ImageDraw.Draw(canvas)
            if a.tag_orn != "none":
                # 参考图：太阳在标语右端的上方，爪印跟随标语走势
                ox = int(W * 0.958)
                oy = band_y - int(ts * 0.58)
                if a.tag_orn == "sun":
                    draw_sun(dd, (ox, oy), max(5, int(ts * 0.19)), tag_col,
                             max(2, int(ts * 0.075)))
                else:
                    draw_paw(dd, (ox - int(ts * 0.25), oy + int(ts * 0.30)),
                             max(8, int(ts * 0.42)), tag_col)
            if a.tag_rule:
                _tf = ImageFont.truetype(sp, ts)
                tw = sum(_tf.getlength(c) for c in a.tag)
                ry = band_y + int(ts * (0.52 if glyph_mode else 0.42))
                if a.tag_pos == "tr":
                    rx1 = int(W * 0.930)
                    rx0 = int(rx1 - tw)
                else:
                    rx0 = int(W * 0.070)
                    rx1 = int(rx0 + tw)
                dd.line((rx0, ry, rx1, ry), fill=tag_col, width=max(1, int(ts * 0.05)))

    # ⑧b 装饰二·角落记号（参考图左下角那三枚爪印）
    if a.marks != "none":
        dd = ImageDraw.Draw(canvas)
        mc = a.marks_color or a.tag_color or txt_col
        if a.marks == "paw":
            for fx, fy, fr in ((0.076, 0.859, 0.017), (0.049, 0.916, 0.018),
                               (0.093, 0.940, 0.014)):
                draw_paw(dd, (int(W * fx), int(H * fy)), int(W * fr), mc)
        else:
            for fx, fy in ((0.070, 0.900), (0.110, 0.930), (0.060, 0.945)):
                r = max(2, int(W * 0.006))
                dd.ellipse((int(W * fx) - r, int(H * fy) - r,
                            int(W * fx) + r, int(H * fy) + r), fill=mc)

    # ⑨ 装饰三：手绘线（最上层，压在字母之上）
    if a.line:
        d = ImageDraw.Draw(canvas)
        y0 = split_y + lower_h * 0.32
        y1 = split_y + lower_h * 0.74
        col = a.line_color or txt_col
        pts = []
        steps = 140
        for i in range(steps + 1):
            t = i / steps
            px = W * (-0.07 + 1.14 * t)
            py = y0 + (y1 - y0) * t + (H * 0.05) * math.sin(t * 3.14)
            pts.append((px, py))
        d.line(pts, fill=col, width=max(2, int(W * 0.0035)), joint="curve")

    # ⑩ 质感
    canvas = _add_grain(canvas, a.grain)
    canvas = _add_vignette(canvas, a.vignette)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=95, subsampling=1)

    print(json.dumps({
        "out": str(out),
        "size": f"{W}x{H}",
        "word": word,
        "font": Path(font_path).name,
        "font_size_px": size,
        "bg": bg,
        "rim": a.rim,
        "mode": a.mode,
        "ink": ink,
        "veil": (a.veil if a.veil is not None
                 else (0.62 if (a.mode == "band" and a.key == "light") else (0.55 if a.mode == "band" else 0.0))),
        "key": a.key,
        "split": a.split,
        "photo_bottom": round(photo_h / H, 3),
        "letter_box": {"x": x, "y": top_y, "w": fmask.width, "h": fmask.height,
                       "width_ratio": round(fmask.width / W, 3),
                       "height_ratio_of_lower": round(fmask.height / lower_h, 3),
                       "bleeds": fmask.width > W},
        "cut": cut_msg,
        "decor": {"tag": a.tag, "rule_left": a.rule_left,
                  "rule_right": a.rule_right, "line": a.line},
    }, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(description="照片字母窗海报排版引擎")
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("prep", help="预处理照片")
    p1.add_argument("image")
    p1.add_argument("-o", "--out", required=True)
    p1.add_argument("--maxlong", type=int, default=2048)
    p1.set_defaults(func=cmd_prep)

    p2 = sub.add_parser("analyze", help="体检 + 主色 + 底色建议")
    p2.add_argument("image")
    p2.add_argument("--colors", type=int, default=8)
    p2.set_defaults(func=cmd_analyze)

    p3 = sub.add_parser("palette", help="只要色板")
    p3.add_argument("image")
    p3.set_defaults(func=cmd_palette)

    p4 = sub.add_parser("poster", help="合成海报")
    p4.add_argument("image")
    p4.add_argument("--word", required=True, help="3-4 个字母最佳，如 CATS / RUN / ACE / LENS")
    p4.add_argument("-o", "--out", required=True)
    p4.add_argument("--size", default=None,
                    help="画布；glyph 默认 1440x1000（约 1.44:1，参考图比例），其余 1152x1536")
    p4.add_argument("--bg", default="#2A211C", help="下半部分纯色底")

    # 字形
    p4.add_argument("--word-width", type=float, default=None, help="单词横向占比，可 >1 出血")
    p4.add_argument("--squeeze", type=float, default=None, help="水平压缩，越小越瘦越高")
    p4.add_argument("--weight", type=int, default=None,
                    help="加粗膨胀 px（绝对值）；不填时按字号比例加粗，glyph 约 3%% 字号")
    p4.add_argument("--fat-x", type=float, default=None,
                    help="横向膨胀量（占字号比例），做 fat-face 海报体骨架；"
                         "glyph 默认 0（无衬线体本来就通体等粗）。0.02 上下更像 fat-face 衬线，纯靠 --weight-pct 整体吹胖")
    p4.add_argument("--weight-pct", type=float, default=None,
                    help="加粗量占字号比例；glyph 默认 0（Arial Black 本来就够重），其余 0（用 --weight 的绝对像素）")
    p4.add_argument("--tracking", type=float, default=None, help="字距（字号倍数）；不填时 glyph 用 -0.05、其余 -0.02")
    p4.add_argument("--height-ratio", type=float, default=None, help="字高至少占下栏的比例，0=不强制")
    p4.add_argument("--max-bleed", type=float, default=None, help="最大出血倍数（宽度/画布宽）")
    p4.add_argument("--font", default=None)

    # 版面
    p4.add_argument("--split", type=float, default=None,
                    help="顶部照片横条占画布高度比例；glyph 默认 0（整幅字母海报，参考图没有上横条）")
    p4.add_argument("--bite", type=float, default=0.03, help="照片向下多压多少（穿插），0=不压")
    p4.add_argument("--letter-gap", type=float, default=None, help="字顶距分界线的画布比例")
    p4.add_argument("--bottom-pad", type=float, default=None, help="字底距画布底的比例（留出主体伸出的空间）")
    p4.add_argument("--rim", type=int, default=0, help="窗框粗细 px，0=无框（示例图均无框）")
    p4.add_argument("--rim-color", default="#F2E8D5")
    p4.add_argument("--ink", default=None, help="字的墨色；默认深底=底色、浅底=同色相近黑")
    p4.add_argument("--key", default="dark", choices=["dark", "light"],
                    help="dark=字压暗（参考图做法）；light=字保留照片原亮度、字外压暗，字里画面最完整")
    p4.add_argument("--veil", type=float, default=None,
                    help="字上压暗强度 0-1：1=实心墨块；0.6 左右字里仍看得见画面；不填=0.85")
    p4.add_argument("--mode", default="glyph", choices=["glyph", "band", "window"],
                    help="glyph=字母本身是照片、底色是纯色、主体从字边渗出去（默认，参考图做法）；"
                         "band=照片整条铺满、词压在上面；window=只有字母里透照片、无渗出")
    p4.add_argument("--window-zoom", type=float, default=1.0, help="字母窗照片放大（叠加在自动对位之上，>1 更近）")
    p4.add_argument("--distress", type=float, default=None,
                    help="老印刷做旧强度 0-1（暖光提亮+提对比+斑块+暖偏）；不填时 glyph 用 0.75、其余 0")
    p4.add_argument("--subject-out", type=float, default=None,
                    help="主体相对字形框放大多少倍；>1 时主体天生越过字顶/字底，才有得可伸。"
                         "不填时 glyph 用 1.18、其余用 1.0")
    p4.add_argument("--window-fill", type=float, default=None,
                    help="主体占满窗口的程度 0-1；不填时 band 模式用 0.75、window 模式用 0.95")
    p4.add_argument("--window-anchor", type=float, default=0.5)
    p4.add_argument("--no-fit", dest="fit_subject", action="store_false",
                    help="不做主体对位：照片严格居中，主体可能落不进字母窗")

    # 立体穿插
    p4.add_argument("--no-cut", dest="cut", action="store_false", help="关闭抠图（退回照片压边模式）")
    p4.add_argument("--no-ground-align", dest="ground_align", action="store_false",
                    help="不对齐地面线。默认会把照片里主体落地的行压到字的基线，爪子才会自然垂到字外")
    p4.add_argument("--shadow", type=float, default=0.42, help="主体接触投影强度 0-1")
    p4.add_argument("--shadow-color", default="#000000", help="投影颜色")
    p4.add_argument("--spill", type=float, default=None,
                    help="主体允许越出字形的半径（相对字高）；glyph 默认 0.16，其余 0.42")
    p4.add_argument("--spill-dir", default=None,
                    choices=["down", "up", "vertical", "left", "right", "sides", "all"],
                    help="主体往哪个方向伸出字母；不填时 glyph 用 all、其余用 down")
    p4.add_argument("--extra", type=float, default=None,
                    help="字母外额外露出主体的深度（相对字高，0=关）。只在单词整体外接框之外生效，"
                         "字缝和字腔一律不动。glyph 默认 0.16：爪、耳、白毛能露在字外，读者一眼看出是两只猫")

    # 装饰
    p4.add_argument("--gutter-fill", type=float, default=None,
                    help="字缝下段允许主体填进去的比例 0-1；glyph 默认 0.25，0=字缝保持干净。"
                         "字腔（A 的三角）永远不填")
    p4.add_argument("--tag-orn", default="none", choices=["none", "sun", "paw"],
                    help="标语旁的小涂鸦；参考图 Sunny Days 右边有个小太阳")
    p4.add_argument("--tag-rule", action="store_true", help="标语下方加一道细横线")
    p4.add_argument("--marks", default="none", choices=["none", "paw", "dot"],
                    help="角落小记号；paw = 左下角三枚爪印")
    p4.add_argument("--marks-color", default=None)
    p4.add_argument("--tag", default=None, help="手写标语，如 \"Keep Going\"")
    p4.add_argument("--tag-pos", default="tr", choices=["tr", "tl", "br"])
    p4.add_argument("--tag-size", type=float, default=None,
                    help="标语字号占画布宽比例；glyph 默认 0.046，其余 0.040")
    p4.add_argument("--tag-rotate", type=float, default=-7.0, help="标语倾斜角度")
    p4.add_argument("--tag-color", default=None, help="形如 \"232,84,42\" 的 RGB")
    p4.add_argument("--rule-left", default=None, help="底部左小字，如 \"TENNIS / DISCIPLINE / LIFE\"")
    p4.add_argument("--rule-right", default=None, help="底部右小字")
    p4.add_argument("--rule-size", type=float, default=0.0135)
    p4.add_argument("--rule-color", default=None)
    p4.add_argument("--line", action="store_true", help="加一条手绘曲线穿过字母")
    p4.add_argument("--line-color", default=None)

    # 质感
    p4.add_argument("--grain", type=float, default=0.55, help="颗粒 0-1")
    p4.add_argument("--vignette", type=float, default=0.18, help="暗角 0-1")
    p4.set_defaults(func=cmd_poster)

    a = p.parse_args()
    for attr in ("tag_color", "rule_color", "line_color"):
        v = getattr(a, attr, None)
        if isinstance(v, str):
            setattr(a, attr, tuple(int(x) for x in v.split(",")))
    a.func(a)


if __name__ == "__main__":
    main()
