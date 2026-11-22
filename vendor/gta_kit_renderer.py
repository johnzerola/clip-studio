#!/usr/bin/env python3
"""
Motor do Kit GTA 6 com Claude.

Uso:
    python3 motor/gerar_video.py roteiro.json [--saida video.mp4] [--previa]

Lê o roteiro.json (cenas + falas + efeitos), a narração (MP3 do ElevenLabs)
e a gameplay, e gera um MP4 vertical 1080x1920 com:
  - cortes no ritmo da narração (sincronizados pelas pausas da voz)
  - zoom lento constante + "punch" nas transições
  - legenda palavra a palavra (1 a 3 palavras), destaque amarelo/rosa
  - interface do jogo animada (logo, cronômetro, setas, estrelas, avisos,
    dinheiro, cards, fatos, números, moldura, rota, pin, título)
  - marca d'água com o @ do canal
  - botão "Inscreva-se" com clique no final

Precisa só de: Python 3, Pillow, numpy e ffmpeg.
"""
import json, math, os, re, subprocess, sys, argparse, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

KIT = os.environ["CODEX_GTA_ASSETS"]
W, H, FPS = 1080, 1920, 30
OVER = 1.12                     # margem para o zoom (fonte é renderizada 12% maior)
BW, BH = int(W * OVER) // 2 * 2, int(H * OVER) // 2 * 2

AMARELO = (255, 214, 10)
ROSA = (255, 46, 160)
BRANCO = (255, 255, 255)
PRETO = (0, 0, 0)
VERDE = (40, 230, 110)
VERMELHO = (235, 40, 60)
LARANJA = (255, 170, 30)

FONTE_LEGENDA = os.path.join(KIT, "estilo", "fontes", "ArchivoBlack-Regular.ttf")
FONTE_UI = os.path.join(KIT, "estilo", "fontes", "Montserrat.ttf")
_font_cache = {}
_video_filters = None


def available_video_filters():
    global _video_filters
    if _video_filters is None:
        listing = subprocess.check_output(["ffmpeg", "-hide_banner", "-filters"], text=True)
        _video_filters = set(re.findall(r"^\s*[.TSC]{2,3}\s+(\w+)\s", listing, re.MULTILINE))
    return _video_filters


def fonte(caminho, tam, peso=None):
    k = (caminho, tam, peso)
    if k not in _font_cache:
        f = ImageFont.truetype(caminho, tam)
        if peso:
            try:
                f.set_variation_by_name(peso)
            except Exception:
                pass
        _font_cache[k] = f
    return _font_cache[k]


def ui(tam, peso="ExtraBold"):
    return fonte(FONTE_UI, tam, peso)


FONTE_HUD = os.path.join(KIT, "estilo", "fontes", "Roboto.ttf")


def hud(tam, peso=800, largura=75):
    """fonte condensada estilo interface do GTA"""
    k = ("hud", tam, peso, largura)
    if k not in _font_cache:
        f = ImageFont.truetype(FONTE_HUD, tam)
        try:
            f.set_variation_by_axes([peso, largura])
        except Exception:
            pass
        _font_cache[k] = f
    return _font_cache[k]


# ----------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_back(x):
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_expo(x):
    x = clamp(x)
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


def ease_in_out(x):
    x = clamp(x)
    return 3 * x * x - 2 * x * x * x


# ----------------------------------------------------------------- áudio
def duracao_midia(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nk=1:nw=1", path], capture_output=True, text=True).stdout
    return float(out.strip())


def detectar_pausas(audio, ruido="-32dB", minimo=0.16):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", audio, "-af",
                        f"silencedetect=noise={ruido}:d={minimo}", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r)]
    fim = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r)]
    pausas = []
    for i, s in enumerate(ini):
        e = fim[i] if i < len(fim) else s + minimo
        pausas.append((s, e))
    return pausas


def volume_medio(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-t", "60", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r)
    return float(m.group(1)) if m else -14.0


def escolher_musica(R):
    m = R.get("musica", "auto")
    if not m or str(m).lower() in ("nenhuma", "none", "false"):
        return None
    pasta = os.path.join(KIT, "assets", "musicas")
    if str(m).lower() == "auto":
        opcoes = sorted(f for f in os.listdir(pasta) if f.lower().endswith((".mp3", ".wav", ".m4a"))) if os.path.isdir(pasta) else []
        if not opcoes:
            return None
        k = sum(ord(ch) for ch in R.get("titulo", "")) % len(opcoes)
        return os.path.join(pasta, opcoes[k])
    for p in (m, os.path.join(pasta, m)):
        if os.path.exists(p):
            return p
    print("Aviso: música não encontrada:", m)
    return None


def peso_texto(t):
    t = limpar_marcas(t)
    return max(1, len(re.sub(r"\s+", " ", t)))


def limpar_marcas(t):
    return t.replace("**", "").replace("*", "")


def tempos_das_cenas(cenas, audio):
    """Encontra o início/fim de cada cena casando as pausas da voz com o tamanho de cada fala."""
    dur = duracao_midia(audio)
    pausas = detectar_pausas(audio)
    # início e fim da fala (ignora silêncio no começo/fim)
    fala_ini, fala_fim = 0.0, dur
    if pausas and pausas[0][0] < 0.05:
        fala_ini = pausas[0][1]
        pausas = pausas[1:]
    if pausas and pausas[-1][1] >= dur - 0.05:
        fala_fim = pausas[-1][0]
        pausas = pausas[:-1]
    pesos = [peso_texto(c["fala"]) for c in cenas]
    total = sum(pesos)
    esperado, acc = [], 0
    for p in pesos[:-1]:
        acc += p
        esperado.append(fala_ini + (fala_fim - fala_ini) * acc / total)
    candidatos = [((s + e) / 2, e - s) for s, e in pausas]
    limites, usado, ultimo = [], set(), fala_ini
    for i, alvo in enumerate(esperado):
        janela = (fala_fim - fala_ini) * 0.12 + 0.6
        melhor, mscore = None, 1e9
        for j, (c, d) in enumerate(candidatos):
            if j in usado or c <= ultimo + 0.35:
                continue
            dist = abs(c - alvo)
            if dist > janela:
                continue
            score = dist - min(d, 0.6) * 0.8          # pausas maiores = fim de frase
            if score < mscore:
                melhor, mscore = j, score
        if melhor is None:
            t = max(alvo, ultimo + 0.4)
        else:
            usado.add(melhor)
            t = candidatos[melhor][0]
        limites.append(t)
        ultimo = t
    bordas = [0.0] + limites + [dur]
    # falas: janelas de voz dentro de cada cena
    tempos = []
    for i in range(len(cenas)):
        a, b = bordas[i], bordas[i + 1]
        va = fala_ini if i == 0 else a
        vb = fala_fim if i == len(cenas) - 1 else b
        # recorta pausas das bordas
        for s, e in pausas:
            if abs(((s + e) / 2) - a) < 0.05:
                va = max(va, e)
            if abs(((s + e) / 2) - b) < 0.05:
                vb = min(vb, s)
        tempos.append({"ini": a, "fim": b, "voz_ini": va, "voz_fim": max(va + 0.3, vb)})
    return tempos, dur, pausas


# ----------------------------------------------------------------- legendas
def quebrar_em_blocos(fala, max_palavras=3, max_chars=15):
    """Divide a fala em blocos de 1-3 palavras. *palavra* = amarelo, **palavra** = rosa."""
    tokens = []
    for m in re.finditer(r"\*\*(.+?)\*\*([^\s*]*)|\*(.+?)\*([^\s*]*)|(\S+)", fala):
        if m.group(1):
            ws, cor, suf = m.group(1).split(), ROSA, m.group(2)
        elif m.group(3):
            ws, cor, suf = m.group(3).split(), AMARELO, m.group(4)
        else:
            ws, cor, suf = [m.group(5)], BRANCO, ""
        for j, w in enumerate(ws):
            tokens.append((w + (suf if j == len(ws) - 1 else ""), cor))
    blocos, atual = [], []
    for w, cor in tokens:
        tam = sum(len(x[0]) + 1 for x in atual) + len(w)
        if atual and (len(atual) >= max_palavras or tam > max_chars):
            blocos.append(atual)
            atual = []
        atual.append((w, cor))
        if re.search(r"[.!?,;:]$", w) and len(atual) >= 1:
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)
    # evita bloco final com 1 palavra curta sozinha
    if len(blocos) > 1 and len(blocos[-1]) == 1 and len(blocos[-1][0][0]) <= 3 and len(blocos[-2]) < 3:
        blocos[-2] += blocos.pop()
    return blocos


def montar_legendas(cenas, tempos):
    leg = []
    for c, t in zip(cenas, tempos):
        blocos = quebrar_em_blocos(c["fala"])
        pesos = [sum(len(w) + 2 for w, _ in b) for b in blocos]
        tot = sum(pesos)
        a, b = t["voz_ini"], t["voz_fim"]
        acc = a
        for bl, p in zip(blocos, pesos):
            d = (b - a) * p / tot
            leg.append({"ini": acc, "fim": acc + d, "palavras": bl, "limite": t["fim"]})
            acc += d
    # cada legenda fica até a próxima começar (sem buraco), máx +0.5s
    for i in range(len(leg) - 1):
        leg[i]["fim"] = min(leg[i + 1]["ini"], leg[i]["fim"] + 0.5, leg[i]["limite"])
    return leg


def desenhar_texto_contorno(img, xy, texto, f, cor, contorno=9, sombra=True, anchor="la"):
    d = ImageDraw.Draw(img)
    x, y = xy
    if sombra:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((x + 4, y + 8), texto, font=f, fill=(0, 0, 0, 170), anchor=anchor,
                                stroke_width=contorno, stroke_fill=(0, 0, 0, 170))
        sh = sh.filter(ImageFilter.GaussianBlur(6))
        img.alpha_composite(sh)
    d.text((x, y), texto, font=f, fill=cor + (255,), anchor=anchor, stroke_width=contorno, stroke_fill=(0, 0, 0, 255))


def brilho_por_cima(img, glow, forca=1.0):
    """Aplica 'glow' por cima de 'img' em modo screen (clareia e dá brilho sem tampar o desenho)."""
    from PIL import ImageChops
    g = np.asarray(glow).astype(np.float32) / 255.0
    rgb_g = g[..., :3] * g[..., 3:4] * forca
    base = np.asarray(img).astype(np.float32) / 255.0
    rgb = 1 - (1 - base[..., :3]) * (1 - np.clip(rgb_g, 0, 1))
    alpha = np.maximum(base[..., 3:4], np.clip(g[..., 3:4] * forca * 0.9, 0, 1))
    out = np.concatenate([rgb, alpha], axis=2)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGBA")


_cache_leg = {}
BRILHO_LEGENDA = 1.0      # 0 = sem brilho; 1 = padrão


def render_bloco_legenda(palavras, tam=84):
    chave = (tuple(palavras), tam)
    if chave in _cache_leg:
        return _cache_leg[chave]
    f = fonte(FONTE_LEGENDA, tam)
    textos = [re.sub(r"[.,;:]+$", "", w).upper() for w, _ in palavras]
    esp = int(tam * 0.28)
    larg = [f.getbbox(t)[2] - f.getbbox(t)[0] for t in textos]
    total = sum(larg) + esp * (len(textos) - 1)
    escala = 1.0
    if total > W * 0.86:
        escala = W * 0.86 / total
        f = fonte(FONTE_LEGENDA, int(tam * escala))
        esp = int(esp * escala)
        larg = [f.getbbox(t)[2] - f.getbbox(t)[0] for t in textos]
        total = sum(larg) + esp * (len(textos) - 1)
    pad = 40
    img = Image.new("RGBA", (int(total + pad * 2), int(tam * escala * 1.6 + pad * 2)), (0, 0, 0, 0))
    # brilho (glow) atrás das letras, na cor de cada palavra
    if BRILHO_LEGENDA > 0:
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        x = pad
        for (w, cor), t, l in zip(palavras, textos, larg):
            forca = 150 if cor == BRANCO else 230
            gd.text((x - f.getbbox(t)[0], pad), t, font=f, fill=cor + (forca,), stroke_width=int(10 * escala),
                    stroke_fill=cor + (forca,))
            x += l + esp
        g1 = glow.filter(ImageFilter.GaussianBlur(16))
        g2 = glow.filter(ImageFilter.GaussianBlur(6))
        a1 = g1.getchannel("A").point(lambda v: int(v * 0.85 * BRILHO_LEGENDA))
        a2 = g2.getchannel("A").point(lambda v: int(v * 0.35 * BRILHO_LEGENDA))
        g1.putalpha(a1)
        g2.putalpha(a2)
        img.alpha_composite(g1)
        img.alpha_composite(g2)
    x = pad
    for (w, cor), t, l in zip(palavras, textos, larg):
        desenhar_texto_contorno(img, (x - f.getbbox(t)[0], pad), t, f, cor, contorno=max(6, int(9 * escala)))
        x += l + esp
    _cache_leg[chave] = img
    return img


# ----------------------------------------------------------------- elementos de interface
def painel(texto, tam=46, cor=AMARELO, sub=None, icone=None):
    """Painel no estilo da interface do GTA 6: fundo escuro translúcido, borda fina, barra de cor
    na esquerda e texto condensado em maiúsculas."""
    f1 = hud(tam, 800, 75)
    f2 = hud(int(tam * 0.62), 600, 80)
    t1 = texto.upper()
    t2 = sub.upper() if sub else None
    w1 = f1.getlength(t1)
    w2 = f2.getlength(t2) if t2 else 0
    pad_x, pad_y = 34, 20
    w = int(max(w1, w2) + pad_x * 2 + 18)
    h = int(tam * 1.05 + pad_y * 2 + (tam * 0.8 if t2 else 0))
    img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((22, 26, 20 + w, 26 + h), 10, fill=(0, 0, 0, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((20, 20, 20 + w, 20 + h), 10, fill=(14, 16, 22, 215), outline=(255, 255, 255, 70), width=2)
    d.rounded_rectangle((20, 20, 29, 20 + h), 4, fill=cor + (255,))
    y = 20 + pad_y
    if t2:
        d.text((20 + pad_x + 12, y - 2), t2, font=f2, fill=(190, 194, 205, 255))
        y += tam * 0.8
    d.text((20 + pad_x + 12, y - tam * 0.12), t1, font=f1, fill=BRANCO + (255,))
    return img


def pill(texto, f, cor_borda=AMARELO, fundo=(10, 10, 14, 225), pad=(30, 16), raio=None, cor_txt=BRANCO, borda=5):
    bb = f.getbbox(texto)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    w, h = tw + pad[0] * 2, th + pad[1] * 2
    raio = raio if raio is not None else h // 2
    img = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 10, 10 + w, 10 + h), raio, fill=fundo, outline=cor_borda + (255,), width=borda)
    d.text((10 + pad[0] - bb[0], 10 + pad[1] - bb[1]), texto, font=f, fill=cor_txt + (255,))
    return img


def circulo_icone(cor, simbolo, tam=150):
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, tam - 6, tam - 6), fill=cor + (255,), outline=(0, 0, 0, 255), width=6)
    c = tam / 2
    s = tam * 0.27
    preto = (15, 15, 15, 255)
    if simbolo in ("esquerda", "direita"):
        sx = -1 if simbolo == "esquerda" else 1
        # seta curva estilo GPS
        d.line([(c - sx * s * 0.6, c + s), (c - sx * s * 0.6, c - s * 0.1), (c + sx * s * 0.5, c - s * 0.1)],
               fill=preto, width=int(tam * 0.1), joint="curve")
        d.polygon([(c + sx * s * 0.45, c - s * 0.65), (c + sx * s * 1.05, c - s * 0.1), (c + sx * s * 0.45, c + s * 0.45)], fill=preto)
    elif simbolo == "frente":
        d.line([(c, c + s), (c, c - s * 0.3)], fill=preto, width=int(tam * 0.1))
        d.polygon([(c - s * 0.6, c - s * 0.2), (c, c - s * 1.0), (c + s * 0.6, c - s * 0.2)], fill=preto)
    elif simbolo == "alerta":
        d.polygon([(c, c - s * 1.0), (c + s * 1.05, c + s * 0.8), (c - s * 1.05, c + s * 0.8)], fill=BRANCO + (255,))
        d.rectangle((c - s * 0.1, c - s * 0.45, c + s * 0.1, c + s * 0.25), fill=cor + (255,))
        d.ellipse((c - s * 0.12, c + s * 0.38, c + s * 0.12, c + s * 0.62), fill=cor + (255,))
    elif simbolo == "check":
        d.line([(c - s * 0.8, c), (c - s * 0.2, c + s * 0.6), (c + s * 0.9, c - s * 0.6)], fill=BRANCO + (255,), width=int(tam * 0.11), joint="curve")
    elif simbolo == "x":
        w_ = int(tam * 0.11)
        d.line([(c - s * 0.7, c - s * 0.7), (c + s * 0.7, c + s * 0.7)], fill=BRANCO + (255,), width=w_)
        d.line([(c + s * 0.7, c - s * 0.7), (c - s * 0.7, c + s * 0.7)], fill=BRANCO + (255,), width=w_)
    elif simbolo == "cifrao":
        f = ui(int(tam * 0.6), "Black")
        d.text((c, c), "$", font=f, fill=BRANCO + (255,), anchor="mm")
    elif simbolo == "proibido":
        d.ellipse((c - s, c - s, c + s, c + s), outline=BRANCO + (255,), width=int(tam * 0.08))
        d.line([(c - s * 0.7, c + s * 0.7), (c + s * 0.7, c - s * 0.7)], fill=BRANCO + (255,), width=int(tam * 0.08))
    return img


def estrela(d, cx, cy, r, cor, contorno=PRETO):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=cor + (255,), outline=contorno + (255,))


def colar(base, img, cx, cy, escala=1.0, alpha=1.0, rot=0):
    if escala <= 0.01 or alpha <= 0.01:
        return
    if escala != 1.0:
        img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))), Image.BILINEAR)
    if rot:
        img = img.rotate(rot, resample=Image.BILINEAR, expand=True)
    if alpha < 1.0:
        a = img.getchannel("A").point(lambda v: int(v * alpha))
        img = img.copy()
        img.putalpha(a)
    x, y = int(cx - img.width / 2), int(cy - img.height / 2)
    base.alpha_composite(img, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))


def entrar(base, img, cx, cy, t, rest, direcao=(0, 1), dist=80, escala=1.0, dur=0.34, rot=0):
    """Entrada profissional: desliza rápido e para seco (sem quicar), com rastro de movimento
    (motion blur) e fade. Saída: some rápido subindo um pouco."""
    k = ease_expo(t / dur)
    a = clamp(t / 0.10)
    dx, dy = direcao
    sc = escala * (0.93 + 0.07 * k)
    if rest < 0.16:
        e = 1 - rest / 0.16
        a *= 1 - e
        cy -= 30 * e
        sc *= 1 - 0.03 * e
    if a <= 0.01:
        return
    if k < 0.97:
        for g in (3, 2, 1):
            kg = ease_expo(max(0.0, t - g * 0.018) / dur)
            colar(base, img, cx + dx * dist * (1 - kg), cy + dy * dist * (1 - kg), escala * (0.93 + 0.07 * kg),
                  alpha=a * 0.22, rot=rot)
    colar(base, img, cx + dx * dist * (1 - k), cy + dy * dist * (1 - k), sc, alpha=a, rot=rot)


def anim_entrada(t, dur=0.32):
    """escala com 'pop' (overshoot)"""
    return ease_out_back(t / dur) if t < dur else 1.0


def anim_saida(t_rest, dur=0.18):
    return clamp(t_rest / dur)


_logos = {}


def logo(nome):
    if nome not in _logos:
        p = os.path.join(KIT, "assets", "logos", f"{nome}-logo.png")
        _logos[nome] = Image.open(p).convert("RGBA")
    return _logos[nome]


class Efeitos:
    """Desenha cada tipo de efeito. t = segundos desde que o efeito começou; rest = segundos até acabar."""

    def __init__(self, ef):
        self.ef = ef
        self.cache = {}

    def desenhar(self, img, t, rest, dur):
        tipo = self.ef["tipo"]
        fn = getattr(self, "e_" + tipo, None)
        if fn is None:
            return
        fn(img, t, rest, dur)

    def pos(self, padrao_y):
        return self.ef.get("x", 0.5) * W, self.ef.get("y", padrao_y) * H

    # --- logo do GTA VI (ou rockstar) no topo: entra "batendo" na tela com rastro de zoom,
    #     trava com tranco + brilho e depois fica viva com reflexo de luz passando
    def e_logo(self, img, t, rest, dur):
        nome = self.ef.get("imagem", "gta6")
        if "img" not in self.cache:
            l = logo(nome)
            alvo = self.ef.get("largura", 0.62) * W
            im = l.resize((int(alvo), int(l.height * alvo / l.width)), Image.LANCZOS)
            self.cache["img"] = im
            alpha = im.getchannel("A")
            pad = 90
            # brilho colorido (as próprias cores da logo, mais claras) + halo branco
            cores = Image.blend(im.convert("RGB"), Image.new("RGB", im.size, (255, 255, 255)), 0.25)
            cores.putalpha(alpha)
            g = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
            g.alpha_composite(cores, (pad, pad))
            largo = g.filter(ImageFilter.GaussianBlur(38))
            perto = g.filter(ImageFilter.GaussianBlur(12))
            perto.putalpha(perto.getchannel("A").point(lambda v: int(v * 0.6)))
            largo.alpha_composite(perto)
            self.cache["glow"] = largo
            # versões da logo com brilho por cima (fraco e forte) para animar
            sobre = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
            sobre.alpha_composite(im, (pad, pad))
            sobre_g = g.filter(ImageFilter.GaussianBlur(14))
            self.cache["logo_brilho"] = [brilho_por_cima(sobre, sobre_g, f).crop((pad, pad, pad + im.width, pad + im.height))
                                         for f in (0.25, 0.45, 0.7)]
            self.cache["alpha"] = np.asarray(alpha).astype(np.float32) / 255.0
        im = self.cache["img"]
        cx, cy = self.pos(0.2)
        T = 0.26                      # tempo até bater
        a = clamp(t / 0.06)
        if rest < 0.18:               # saída: sobe e some
            e = 1 - rest / 0.18
            a *= 1 - e
            cy -= 50 * e
        if a <= 0.01:
            return
        if t < T:
            k = ease_expo(t / T)
            esc = 2.1 - 1.1 * k
            rot = -10 * (1 - k)
            for g_ in (4, 3, 2, 1):   # rastro de zoom
                kg = ease_expo(max(0.0, t - g_ * 0.022) / T)
                colar(img, im, cx, cy, 2.1 - 1.1 * kg, alpha=a * 0.16, rot=-10 * (1 - kg))
            colar(img, im, cx, cy, esc, alpha=a, rot=rot)
            return
        tb = t - T                    # depois de bater
        # tranco
        amp = 16 * math.exp(-tb * 14)
        ox, oy = math.sin(tb * 95) * amp, math.cos(tb * 81) * amp
        # respiração leve + deriva
        esc = 1.0 + 0.06 * math.exp(-tb * 18) * 0 + 0.012 * math.sin(tb * 2.4) + 0.01 * tb
        cy2 = cy + math.sin(tb * 1.5) * 6
        # brilho do impacto (forte e some) + brilho base suave
        gl = min(1.0, 0.6 + 0.12 * math.sin(tb * 3.2) + 0.6 * math.exp(-tb * 6))
        colar(img, self.cache["glow"], cx + ox, cy2 + oy, esc * 1.04, alpha=a * gl)
        if gl > 0.75:   # segunda camada no impacto
            colar(img, self.cache["glow"], cx + ox, cy2 + oy, esc * 1.12, alpha=a * (gl - 0.75) * 2)
        # reflexo de luz passando (no impacto e depois a cada 2,2 s)
        nivel = 2 if tb < 0.25 else (1 if math.sin(tb * 3.2) > 0.3 else 0)
        el = self.cache["logo_brilho"][nivel]
        fase = tb % 2.2
        if fase < 0.55:
            al = self.cache["alpha"]
            hh, ww = al.shape
            xs = np.arange(ww)[None, :] + np.arange(hh)[:, None] * 0.45
            pos = -0.3 * ww + (ww * 1.9) * (fase / 0.55)
            faixa = np.clip(1 - np.abs(xs - pos) / (ww * 0.07), 0, 1) ** 1.5
            m = (faixa * al * 200).astype(np.uint8)
            luz = Image.new("RGBA", (ww, hh), (255, 255, 255, 0))
            luz.putalpha(Image.fromarray(m))
            el = el.copy()
            el.alpha_composite(luz)
        colar(img, el, cx + ox, cy2 + oy, esc, alpha=a)

    # --- título grande no topo ("GTA V" / "GTA VI")
    def e_titulo(self, img, t, rest, dur):
        texto = self.ef.get("texto", "GTA VI")
        if "img" not in self.cache:
            f = ui(int(self.ef.get("tamanho", 120)), "Black")
            bb = f.getbbox(texto)
            im = Image.new("RGBA", (bb[2] + 80, bb[3] + 80), (0, 0, 0, 0))
            cor = tuple(self.ef.get("cor", BRANCO))
            desenhar_texto_contorno(im, (40, 30), texto, f, cor, contorno=7)
            im = im.transform(im.size, Image.AFFINE, (1, 0.18, -im.height * 0.09, 0, 1, 0), Image.BICUBIC)  # itálico
            self.cache["img"] = im
        cx, cy = self.pos(0.11)
        entrar(img, self.cache["img"], cx, cy, t, rest, direcao=(-1, 0), dist=120)

    # --- cronômetro circular em contagem regressiva
    def e_cronometro(self, img, t, rest, dur):
        de = float(self.ef.get("de", 60))
        restante = max(0.0, de - t * self.ef.get("velocidade", 1.0))
        tam = 300
        im = Image.new("RGBA", (tam + 20, tam + 20), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((10, 10, tam + 10, tam + 10), fill=(14, 16, 26, 235), outline=VERMELHO + (255,), width=16)
        frac = restante / de
        d.arc((22, 22, tam - 2, tam - 2), -90, -90 + 360 * frac, fill=(255, 255, 255, 230), width=6)
        m, s = int(restante // 60), restante % 60
        txt = f"{m}:{int(s):02d}"
        d.text((tam / 2 + 2, tam / 2 + 22), txt, font=ui(96, "Black"), fill=BRANCO + (255,), anchor="mm")
        ix, iy = tam / 2 + 10, tam / 2 - 62
        d.ellipse((ix - 17, iy - 15, ix + 17, iy + 19), outline=AMARELO + (255,), width=5)
        d.rectangle((ix - 6, iy - 25, ix + 6, iy - 18), fill=AMARELO + (255,))
        d.line([(ix, iy + 2), (ix, iy - 8)], fill=AMARELO + (255,), width=4)
        cent = int((s - int(s)) * 10)
        d.text((tam / 2 + 122, tam / 2 + 44), f".{cent}", font=ui(40, "Black"), fill=LARANJA + (255,), anchor="mm")
        cx, cy = self.pos(0.2)
        entrar(img, im, cx, cy, t, rest, direcao=(0, -1), dist=70)

    # --- seta de direção (esquerda / direita / frente)
    def e_seta(self, img, t, rest, dur):
        if "img" not in self.cache:
            self.cache["img"] = circulo_icone(AMARELO, self.ef.get("dir", "direita"), 160)
        cx, cy = self.pos(0.3)
        sx = -1 if self.ef.get("dir") == "esquerda" else (1 if self.ef.get("dir") == "direita" else 0)
        entrar(img, self.cache["img"], cx, cy, t, rest, direcao=(-sx, 0 if sx else 1), dist=90)

    # --- ícone redondo (alerta, check, x, cifrao, proibido)
    def e_icone(self, img, t, rest, dur):
        simb = self.ef.get("simbolo", "alerta")
        cores = {"alerta": VERMELHO, "check": (30, 180, 90), "x": VERMELHO, "cifrao": (30, 180, 90), "proibido": VERMELHO}
        if "img" not in self.cache:
            self.cache["img"] = circulo_icone(cores.get(simb, VERMELHO), simb, 150)
        cx, cy = self.pos(0.3)
        entrar(img, self.cache["img"], cx, cy, t, rest, direcao=(0, -1), dist=60)

    def e_alerta(self, img, t, rest, dur):
        self.ef.setdefault("simbolo", "alerta")
        self.e_icone(img, t, rest, dur)

    # --- estrelas de procurado (aparecem uma a uma)
    def e_estrelas(self, img, t, rest, dur):
        q = int(self.ef.get("qtd", 5))
        total = int(self.ef.get("total", max(5, q)))
        r = 42
        w = total * r * 2.3 + 40
        im = Image.new("RGBA", (int(w), 150), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((4, 18, w - 4, 132), 18, fill=(10, 10, 14, 220), outline=ROSA + (255,), width=5)
        for i in range(total):
            cx = 20 + r * 1.15 + i * r * 2.3
            aceso = t > 0.15 + i * 0.16 and i < q
            sc = (0.75 + 0.25 * ease_expo((t - 0.15 - i * 0.16) / 0.2)) if aceso else 1
            pisca = aceso and (int(t * 4) % 2 == 0) and self.ef.get("piscar", True)
            cor = BRANCO if (aceso and not pisca) else ((255, 240, 120) if aceso else (70, 70, 80))
            estrela(d, cx, 75, r * (sc if aceso else 0.9), cor)
        cx, cy = self.pos(0.22)
        entrar(img, im, cx, cy, t, rest, direcao=(0, -1), dist=70)

    # --- aviso em pílula ("Motor danificado", "Sem gasolina")
    def e_aviso(self, img, t, rest, dur):
        if "img" not in self.cache:
            cor = tuple(self.ef.get("cor", VERMELHO))
            self.cache["img"] = painel(self.ef.get("texto", "Aviso"), 60, cor=cor, sub=self.ef.get("sub"))
        cx, cy = self.pos(0.24)
        entrar(img, self.cache["img"], cx, cy, t, rest, direcao=(1, 0), dist=140)

    # --- dinheiro contando
    def e_dinheiro(self, img, t, rest, dur):
        de, para = float(self.ef.get("de", 0)), float(self.ef.get("para", 1000))
        k = ease_in_out((t - 0.2) / max(0.4, min(dur - 0.4, 1.4)))
        v = de + (para - de) * k
        cor = (60, 230, 120) if para >= de else VERMELHO
        txt = "$" + f"{int(round(v)):,}".replace(",", ".")
        f = ui(84, "Black")
        bb = f.getbbox(txt)
        im = Image.new("RGBA", (bb[2] + 90, bb[3] + 60), (0, 0, 0, 0))
        desenhar_texto_contorno(im, (40, 20), txt, f, cor if k > 0.02 else BRANCO, contorno=6)
        cx, cy = self.pos(0.22)
        entrar(img, im, cx, cy, t, rest, direcao=(0, 1), dist=70)

    # --- card de item/veículo (título + subtítulo)
    def e_card(self, img, t, rest, dur):
        if "img" not in self.cache:
            tt, sub = self.ef.get("titulo", ""), self.ef.get("sub", "")
            cor = tuple(self.ef.get("cor", AMARELO))
            card = painel(sub or tt, 68, cor=cor, sub=tt if sub else None)
            card.thumbnail((round(W * 0.83), H), Image.Resampling.LANCZOS)
            self.cache["img"] = card
        cx, cy = self.pos(0.22)
        entrar(img, self.cache["img"], cx, cy, t, rest, direcao=(-1, 0), dist=150)

    # --- selo "FATO 3/10" com barra de progresso (canto superior esquerdo)
    def e_fato(self, img, t, rest, dur):
        n, tot = int(self.ef.get("n", 1)), int(self.ef.get("total", 10))
        im = Image.new("RGBA", (520, 140), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((8, 8, 118, 118), 22, fill=(20, 20, 28, 235), outline=AMARELO + (255,), width=5)
        d.text((63, 63), str(n), font=ui(68, "Black"), fill=AMARELO + (255,), anchor="mm")
        d.text((140, 30), f"FATO {n}/{tot}", font=ui(38, "Black"), fill=BRANCO + (255,), stroke_width=4, stroke_fill=(0, 0, 0, 255))
        seg = 300 / tot
        for i in range(tot):
            cor = (ROSA if i < n - 1 else AMARELO if i == n - 1 else (90, 90, 100))
            d.rounded_rectangle((140 + i * seg, 88, 140 + (i + 1) * seg - 6, 100), 4, fill=cor + (255,))
        cx = 40 + 520 * 0.8 - 560 * (1 - ease_out(t / 0.3))
        colar(img, im, cx, 0.075 * H + 70, 1.6, alpha=anim_saida(rest))

    # --- número gigante laranja (contagens, rankings)
    def e_numero(self, img, t, rest, dur):
        txt = str(self.ef.get("n", "1"))
        if "img" not in self.cache:
            f = fonte(FONTE_LEGENDA, int(self.ef.get("tamanho", 330)))
            bb = f.getbbox(txt)
            im = Image.new("RGBA", (bb[2] + 120, bb[3] + 120), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            # degradê amarelo->laranja
            mask = Image.new("L", im.size, 0)
            ImageDraw.Draw(mask).text((60, 40), txt, font=f, fill=255)
            grad = Image.new("RGBA", im.size)
            gd = ImageDraw.Draw(grad)
            for y in range(im.height):
                k = y / im.height
                gd.line([(0, y), (im.width, y)], fill=(255, int(225 - 90 * k), int(60 - 40 * k), 255))
            sombra = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ImageDraw.Draw(sombra).text((70, 56), txt, font=f, fill=(120, 40, 0, 255), stroke_width=10, stroke_fill=(60, 20, 0, 255))
            im.alpha_composite(sombra)
            im.paste(grad, (0, 0), mask)
            self.cache["img"] = im
        cx, cy = self.pos(0.2)
        entrar(img, self.cache["img"], cx, cy, t, rest, direcao=(0, 1), dist=110, escala=1 + 0.02 * t, dur=0.4, rot=-4)

    # --- moldura amarela de cantos marcando algo na tela
    def e_moldura(self, img, t, rest, dur):
        x, y = self.ef.get("x", 0.5) * W, self.ef.get("y", 0.45) * H
        w, h = self.ef.get("w", 0.4) * W, self.ef.get("h", 0.25) * H
        k = ease_expo(t / 0.28)
        s = (1.35 - 0.35 * k) * (1 + 0.02 * math.sin(t * 6))
        w2, h2 = w * s / 2, h * s / 2
        d = ImageDraw.Draw(img)
        L = min(w, h) * 0.22
        a = int(255 * anim_saida(rest) * clamp(t / 0.15))
        cor = AMARELO + (a,)
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx_, cy_ = x + sx * w2, y + sy * h2
                d.line([(cx_, cy_), (cx_ - sx * L, cy_)], fill=cor, width=8)
                d.line([(cx_, cy_), (cx_, cy_ - sy * L)], fill=cor, width=8)
        d.rectangle((x - w2, y - h2, x + w2, y + h2), outline=(255, 255, 255, a // 3), width=2)

    # --- rota verde que se desenha (por cima do mapa)
    def e_rota(self, img, t, rest, dur):
        pts = [(p[0] * W, p[1] * H) for p in self.ef.get("pontos", [[0.3, 0.7], [0.5, 0.5], [0.7, 0.3]])]
        k = ease_in_out((t - 0.1) / max(0.6, min(dur * 0.7, 2.2)))
        seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        alvo = sum(seg) * k
        desenho, acc = [pts[0]], 0
        for i, s in enumerate(seg):
            if acc + s <= alvo:
                desenho.append(pts[i + 1])
                acc += s
            else:
                f = (alvo - acc) / s if s else 0
                desenho.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f))
                break
        a = int(255 * anim_saida(rest))
        d = ImageDraw.Draw(img)
        if len(desenho) > 1:
            d.line(desenho, fill=(0, 60, 20, a), width=30, joint="curve")
            d.line(desenho, fill=VERDE + (a,), width=20, joint="curve")
        ex, ey = desenho[-1]
        r = 22 + 4 * math.sin(t * 8)
        d.ellipse((ex - r, ey - r, ex + r, ey + r), fill=BRANCO + (a,), outline=(0, 0, 0, a), width=5)
        fx, fy = pts[-1]
        R = 46 + 8 * math.sin(t * 5)
        d.ellipse((fx - R, fy - R, fx + R, fy + R), outline=BRANCO + (a,), width=6)
        d.ellipse((fx - 16, fy - 16, fx + 16, fy + 16), fill=(20, 20, 20, a))

    # --- pin de localização quicando
    def e_pin(self, img, t, rest, dur):
        x, y = self.ef.get("x", 0.5) * W, self.ef.get("y", 0.4) * H
        b = abs(math.sin(t * 5)) * 22
        s = (0.6 + 0.4 * ease_expo(t / 0.3)) * anim_saida(rest)
        r = 46 * s
        if r < 2:
            return
        d = ImageDraw.Draw(img)
        cor = tuple(self.ef.get("cor", ROSA))
        d.ellipse((x - 30 * s, y - 8 * s, x + 30 * s, y + 8 * s), fill=(0, 0, 0, 110))
        cy = y - b - r * 1.6
        d.polygon([(x - r * 0.75, cy + r * 0.5), (x + r * 0.75, cy + r * 0.5), (x, y - b)], fill=cor + (255,))
        d.ellipse((x - r, cy - r, x + r, cy + r), fill=cor + (255,), outline=BRANCO + (255,), width=6)
        d.ellipse((x - r * 0.38, cy - r * 0.38, x + r * 0.38, cy + r * 0.38), fill=BRANCO + (255,))
        if self.ef.get("texto"):
            if "lbl" not in self.cache:
                self.cache["lbl"] = painel(self.ef["texto"], 48, cor=cor)
            colar(img, self.cache["lbl"], x, cy - r - 60, s)

    # --- texto livre em pílula
    def e_texto(self, img, t, rest, dur):
        if "img" not in self.cache:
            cor = tuple(self.ef.get("cor", AMARELO))
            self.cache["img"] = painel(self.ef.get("texto", ""), int(self.ef.get("tamanho", 64)), cor=cor)
        cx, cy = self.pos(0.22)
        entrar(img, self.cache["img"], cx, cy, t, rest, direcao=(0, 1), dist=70)

    # --- botão inscreva-se com cursor clicando
    def e_inscreva(self, img, t, rest, dur):
        clicado = t > 0.95
        f = ui(54, "Black")
        txt = "Inscrito" if clicado else "Inscreva-se"
        cor_f = (245, 245, 245, 245) if clicado else (230, 20, 40, 255)
        cor_t = (20, 20, 20) if clicado else BRANCO
        bb = f.getbbox(txt)
        w, h = 470, 130
        im = Image.new("RGBA", (w + 30, h + 30), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((15, 15, 15 + w, 15 + h), h // 2, fill=cor_f, outline=(0, 0, 0, 120), width=3)
        d.text((15 + w / 2, 15 + h / 2), txt, font=f, fill=cor_t + (255,), anchor="mm")
        cx, cy = self.pos(0.4)
        aperta = 0.9 if 0.85 < t < 1.0 else 1.0
        entrar(img, im, cx, cy, t, rest, direcao=(0, 1), dist=80, escala=aperta)
        # cursor
        k = ease_in_out((t - 0.2) / 0.6)
        px = cx + 330 - 200 * k
        py = cy + 200 - 150 * k
        d = ImageDraw.Draw(img)
        cur = [(0, 0), (0, 70), (18, 54), (32, 84), (44, 78), (30, 50), (54, 50)]
        sc = 1.15 * (0.85 if 0.85 < t < 1.0 else 1)
        if t > 0.15:
            d.polygon([(px + x * sc, py + y * sc) for x, y in cur], fill=BRANCO + (255,), outline=(0, 0, 0, 255))


# ----------------------------------------------------------------- vídeo base
class FonteVideo:
    """Lê frames (RGB) de um trecho de clipe já recortado para vertical."""

    def __init__(self, caminho, inicio, n_frames, foco_x=0.5, w=BW, h=BH, velocidade=1.0, espelhar=False):
        self.n = n_frames
        self.w, self.h = w, h
        dur = n_frames / FPS * velocidade + 0.5
        ar = w / h
        crop = (f"crop='min(iw,ih*{ar:.5f})':'min(ih,iw/{ar:.5f})':"
                f"'(iw-min(iw,ih*{ar:.5f}))*{clamp(foco_x):.3f}':'(ih-min(ih,iw/{ar:.5f}))/2'")
        vf = [f"fps={FPS / velocidade:.4f}" if velocidade != 1 else f"fps={FPS}", crop,
              "hqdn3d=1.5:1.5:3:3",                       # limpa os blocos de compressão
              f"scale={w}:{h}:flags=lanczos", "cas=0.7",   # nitidez adaptativa (realça sem estourar)
              "unsharp=3:3:0.3:3:3:0.0", "eq=contrast=1.07:saturation=1.10:gamma=0.98",
              "colorbalance=rs=-0.02:bs=0.03:rh=0.03:bh=-0.03",   # sombra fria, luz quente (cara de cinema)
              "vignette=angle=PI/5", "noise=alls=3:allf=t"]
        if velocidade != 1:
            vf.insert(1, f"setpts=PTS/{velocidade}")
        if espelhar:
            vf.append("hflip")
        vf.append(f"tpad=stop_mode=clone:stop_duration=5")
        optional = {"hqdn3d", "eq", "cas", "unsharp", "colorbalance", "vignette", "noise"}
        available = available_video_filters()
        vf = [item for item in vf if item.partition("=")[0] not in optional - available]
        cmd = ["ffmpeg", "-v", "error", "-threads", "2", "-filter_threads", "2", "-ss", f"{max(0, inicio):.3f}",
               "-t", f"{dur:.3f}", "-i", caminho, "-vf", ",".join(vf), "-frames:v", str(n_frames),
               "-threads:v", "2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=w * h * 3)
        self.ultimo = None

    def ler(self):
        raw = self.p.stdout.read(self.w * self.h * 3)
        if len(raw) < self.w * self.h * 3:
            if self.p.wait() or self.ultimo is None:
                raise RuntimeError("O FFmpeg não conseguiu decodificar o trecho de gameplay.")
            return self.ultimo
        self.ultimo = Image.frombuffer("RGB", (self.w, self.h), raw, "raw", "RGB", 0, 1)
        return self.ultimo

    def fechar(self):
        self.p.stdout.close()
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait()


def resolver_clipe(nome, base_dir):
    if os.path.isabs(nome) and os.path.exists(nome):
        return nome
    for d in (base_dir, os.path.join(base_dir, "gameplay"), os.getcwd(), KIT, os.path.join(KIT, "assets", "gameplay")):
        p = os.path.join(d, nome)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"Clipe não encontrado: {nome}")


# ----------------------------------------------------------------- transições
def transicao_da_cena(i, c):
    tr = c.get("transicao")
    if tr == "punch":
        tr = "zoom"
    if tr:
        return tr
    if i == 0:
        return "corte"
    if c.get("revelacao"):
        return "glitch"
    if i % 4 == 0:
        return "zoom" if (i // 4) % 2 == 1 else "whip"
    return "corte"


def desfoque_rapido(img, raio):
    if raio <= 0.3:
        return img
    peq = img.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(raio / 4))
    return peq.resize((W, H), Image.BILINEAR)


def blur_horizontal(img, forca):
    """rastro horizontal (whip pan)"""
    a = np.asarray(img.resize((W // 3, H // 3), Image.BILINEAR)).astype(np.float32)
    n = max(2, int(forca))
    acc = np.zeros_like(a)
    for j in range(n):
        acc += np.roll(a, j - n // 2, axis=1)
    acc /= n
    return Image.fromarray(acc.astype(np.uint8), img.mode).resize((W, H), Image.BILINEAR)


def aplicar_glitch(img, k, semente):
    """RGB separado + faixas deslocadas; k = intensidade 0..1"""
    if k <= 0.02:
        return img
    rng = np.random.default_rng(semente)
    a = np.asarray(img.convert("RGB")).copy()
    dx = int(26 * k)
    out = a.copy()
    out[:, :, 0] = np.roll(a[:, :, 0], dx, axis=1)
    out[:, :, 2] = np.roll(a[:, :, 2], -dx, axis=1)
    for _ in range(int(7 * k) + 1):
        y0 = int(rng.integers(0, H - 60))
        hh = int(rng.integers(20, 140))
        out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], int(rng.integers(-90, 90) * k), axis=1)
    return Image.fromarray(out).convert("RGBA")


SONS = {}


def info_som(nome):
    if not SONS:
        try:
            with open(os.path.join(KIT, "assets", "sfx", "sons.json")) as f:
                SONS.update(json.load(f))
        except Exception:
            pass
    return SONS.get(nome, {"dur": 0.5, "pico": 0.0})


# ----------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roteiro")
    ap.add_argument("--saida", default=None)
    ap.add_argument("--previa", action="store_true", help="gera só imagens de prévia (rápido) em vez do vídeo")
    ap.add_argument("--crf", default="20")
    ap.add_argument("--ate", type=float, default=None, help="gera só os primeiros N segundos (teste rápido)")
    args = ap.parse_args()

    with open(args.roteiro, encoding="utf-8") as f:
        R = json.load(f)
    base_dir = os.path.dirname(os.path.abspath(args.roteiro))
    audio = resolver_clipe(R["audio"], base_dir)
    cenas = R["cenas"]
    saida = args.saida or os.path.join(base_dir, R.get("saida", "video_final.mp4"))

    if R.get("timing"):
        tempos = R["timing"]
        dur_total, pausas = tempos[-1]["fim"], []
    else:
        tempos, dur_total, pausas = tempos_das_cenas(cenas, audio)
    legendas = montar_legendas(cenas, tempos)
    arroba = R.get("arroba", "").strip()
    if arroba and not arroba.startswith("@"):
        arroba = "@" + arroba

    print(f"Narração: {dur_total:.1f}s | {len(cenas)} cenas | {len(legendas)} blocos de legenda")
    for i, (c, t) in enumerate(zip(cenas, tempos)):
        print(f"  cena {i + 1:2d}: {t['ini']:6.2f} -> {t['fim']:6.2f}  {limpar_marcas(c['fala'])[:60]}")

    # efeitos com tempo absoluto
    efeitos = []
    for c, t in zip(cenas, tempos):
        for ef in c.get("efeitos", []):
            ini = t["ini"] + float(ef.get("em", 0.1))
            fim = t["ini"] + float(ef["ate"]) if "ate" in ef else (ini + float(ef["dur"]) if "dur" in ef else t["fim"])
            efeitos.append((ini, fim, Efeitos(dict(ef))))
    if R.get("inscreva", True):
        ini = max(tempos[-1]["ini"] + 0.2, dur_total - 2.4)
        efeitos.append((ini, dur_total + 1, Efeitos({"tipo": "inscreva", "y": 0.42})))

    # efeitos sonoros: escolhidos automaticamente para cada transição/efeito, só em momentos estratégicos.
    # (nome, momento_do_pico, volume, duracao_max)
    sfx = []

    def som(nome, pico_em, vol, dur=None):
        inf = info_som(nome)
        sfx.append((nome, max(0.0, pico_em - inf["pico"]), vol, dur))

    for i, (c, t) in enumerate(zip(cenas, tempos)):
        tr = transicao_da_cena(i, c)
        if i == 0:
            som("whoosh-cinematico", 0.32, 0.45)
        elif tr == "zoom":
            som("whoosh-cinematico", t["ini"], 0.34)
        elif tr == "whip":
            som("whoosh", t["ini"] + 0.02, 0.42)
        elif tr == "glitch":
            som("glitch", t["ini"] + 0.05, 0.26, 0.45)
        elif tr == "flash":
            som("whoosh", t["ini"], 0.5)
        if c.get("revelacao"):
            som("riser", t["ini"], 0.24)
        for ef in c.get("efeitos", []):
            quando = t["ini"] + float(ef.get("em", 0.1))
            tp = ef["tipo"]
            if ef.get("som") is False:
                continue
            if ef.get("som"):
                som(ef["som"], quando + 0.05, 0.5)
            elif tp == "dinheiro":
                som("dinheiro", quando + 0.35, 0.45)
            elif tp == "cronometro":
                d_ef = float(ef.get("dur", t["fim"] - quando))
                som("relogio", quando + info_som("relogio")["pico"], 0.28, min(d_ef, 3.7))
            elif tp == "aviso":
                som("notificacao", quando + 0.08, 0.32)
            elif tp in ("card", "fato", "texto", "estrelas"):
                som("pop", quando + 0.03, 0.26)
            elif tp == "numero":
                som("whoosh", quando + 0.05, 0.38)
    if R.get("inscreva", True):
        som("clique", max(tempos[-1]["ini"] + 0.2, dur_total - 2.4) + 0.9, 0.6)
    # evita sons de interface amontoados (mínimo 0,4 s entre eles)
    ui_sons = {"pop", "notificacao", "clique"}
    filtrado, ultimo_ui = [], -9
    for item in sorted(sfx, key=lambda x: x[1]):
        if item[0] in ui_sons:
            if item[1] - ultimo_ui < 1.2:
                continue
            ultimo_ui = item[1]
        filtrado.append(item)
    sfx = filtrado
    print(f"Efeitos sonoros: {len(sfx)}")

    n_total = int(math.ceil(dur_total * FPS)) + int(0.4 * FPS)

    if args.previa:
        os.makedirs(os.path.join(base_dir, "previa"), exist_ok=True)

    # encoder
    tmp_video = saida + ".tmp_video.mp4"
    enc = None
    if not args.previa:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", str(FPS), "-i", "-", *json.loads(os.environ["CODEX_GTA_ENCODER"]),
                                "-pix_fmt", "yuv420p", tmp_video], stdin=subprocess.PIPE)

    marca = None
    if arroba:
        f = ui(40, "Bold")
        bb = f.getbbox(arroba)
        marca = Image.new("RGBA", (bb[2] + 30, bb[3] + 30), (0, 0, 0, 0))
        ImageDraw.Draw(marca).text((15, 10), arroba, font=f, fill=(255, 255, 255, 150), stroke_width=3, stroke_fill=(0, 0, 0, 110))

    limite_frames = int(args.ate * FPS) if args.ate else None
    frame_global = 0
    previas = []
    ultimo_frame = None
    for i, (c, t) in enumerate(zip(cenas, tempos)):
        fim = t["fim"] if i < len(cenas) - 1 else dur_total + 0.4
        n = int(round(fim * FPS)) - frame_global
        if limite_frames is not None:
            if frame_global >= limite_frames:
                break
            n = min(n, limite_frames - frame_global)
        if n <= 0:
            continue
        clip = resolver_clipe(c.get("clipe", R.get("gameplay", "")), base_dir)
        vel = float(c.get("velocidade", 1.0))
        split = c.get("split")
        if split:
            fa = FonteVideo(clip, float(c.get("inicio", 0)), n, c.get("foco_x", 0.5), w=W, h=H // 2, velocidade=vel)
            clip2 = resolver_clipe(split.get("clipe", clip), base_dir)
            fb = FonteVideo(clip2, float(split.get("inicio", 0)), n, split.get("foco_x", 0.5), w=W, h=H // 2)
        else:
            fa = FonteVideo(clip, float(c.get("inicio", 0)), n, c.get("foco_x", 0.5), velocidade=vel, espelhar=c.get("espelhar", False))
            fb = None
        zoom = c.get("zoom", "in" if i % 2 == 0 else "out")
        tr = transicao_da_cena(i, c)
        tremer = c.get("tremer", False)
        for k in range(n):
            tg = (frame_global + k) / FPS
            tl = k / FPS
            dur_c = n / FPS
            if fb is not None:
                frame = Image.new("RGB", (W, H))
                frame.paste(fa.ler(), (0, 0))
                frame.paste(fb.ler(), (0, H // 2))
                d = ImageDraw.Draw(frame)
                d.rectangle((0, H // 2 - 4, W, H // 2 + 4), fill=(255, 255, 255))
                frame = frame.convert("RGBA")
                for txt, yy in ((split.get("rotulo_cima", "GTA V"), 0.07), (split.get("rotulo_baixo", "GTA VI"), 0.57)):
                    Efeitos({"tipo": "titulo", "texto": txt, "y": yy, "tamanho": 96}).desenhar(frame, tl, 99, dur_c)
            else:
                src = fa.ler()
                p = tl / max(dur_c, 0.01)
                if zoom == "in":
                    z = 1.0 + 0.10 * ease_in_out(p)
                elif zoom == "out":
                    z = 1.10 - 0.10 * ease_in_out(p)
                else:
                    z = 1.04
                if tr == "zoom" and tl < 0.3:
                    z += 0.22 * (1 - ease_expo(tl / 0.3))
                z = min(z, 1.25)
                cw, ch = BW / (z * OVER), BH / (z * OVER)
                ox = (BW - cw) / 2
                oy = (BH - ch) * clamp(float(c.get("foco_y", R.get("foco_y", 0.5))))
                if tremer:
                    ox += math.sin(tg * 37) * 6 + math.sin(tg * 71) * 3
                    oy += math.cos(tg * 29) * 6 + math.cos(tg * 53) * 3
                if tr in ("zoom", "glitch", "whip") and tl < 0.3:   # tranco de câmera no impacto
                    amp = 8 * (1 - tl / 0.3) ** 2
                    ox += math.sin(tl * 90) * amp
                    oy += math.cos(tl * 77) * amp
                ox = min(max(0.0, ox), BW - cw)
                oy = min(max(0.0, oy), BH - ch)
                frame = src.resize((W, H), Image.BILINEAR, box=(ox, oy, ox + cw, oy + ch)).convert("RGBA")
            limpo = frame.copy() if (k == n - 1 or (args.previa and k == n // 2)) else None
            # ---- transições
            if tr == "flash" and tl < 0.14:
                fl = Image.new("RGBA", (W, H), (255, 255, 255, int(120 * (1 - tl / 0.14))))
                frame.alpha_composite(fl)
            elif tr == "zoom" and tl < 0.2 and ultimo_frame is not None:
                k_ = ease_expo(tl / 0.2)
                velho = ultimo_frame.resize((int(W * (1 + 0.35 * k_)), int(H * (1 + 0.35 * k_))), Image.BILINEAR)
                velho = desfoque_rapido(velho.crop(((velho.width - W) // 2, (velho.height - H) // 2,
                                                    (velho.width - W) // 2 + W, (velho.height - H) // 2 + H)), 10 * k_)
                frame = Image.blend(velho.convert("RGBA"), frame, k_)
            elif tr == "zoom" and tl < 0.3:
                frame = Image.blend(desfoque_rapido(frame, 8), frame, ease_expo((tl - 0.2) / 0.1 + 0.2))
            elif tr == "whip" and tl < 0.2 and ultimo_frame is not None:
                k_ = ease_in_out(tl / 0.2)
                comp = Image.new("RGBA", (W, H))
                comp.paste(ultimo_frame, (int(-W * k_), 0))
                comp.paste(frame, (int(W * (1 - k_)), 0))
                frame = blur_horizontal(comp, 6 + 40 * math.sin(math.pi * k_))
            elif tr == "glitch" and tl < 0.24:
                base_g = ultimo_frame if (tl < 0.06 and ultimo_frame is not None) else frame
                frame = aplicar_glitch(base_g, 1 - tl / 0.24, int(tg * 1000))
            # ---- fundo desfocado quando entra um elemento importante (profundidade)
            desf = 0.0
            for ini, fimf, ef in efeitos:
                if ini <= tg < fimf and ef.ef.get("desfocar", ef.ef["tipo"] in ("numero",)):
                    desf = max(desf, ease_out((tg - ini) / 0.25) * clamp((fimf - tg) / 0.2))
            if desf > 0.02:
                fundo = desfoque_rapido(frame, 22 * desf)
                escuro = Image.new("RGBA", (W, H), (0, 0, 0, int(70 * desf)))
                fundo.alpha_composite(escuro)
                frame = fundo
            # efeitos
            for ini, fimf, ef in efeitos:
                if ini <= tg < fimf:
                    ef.desenhar(frame, tg - ini, fimf - tg, fimf - ini)
            # legenda
            ylg_atual = H * 0.5 if fb is not None else float(c.get("legenda_y", R.get("legenda_y", 0.70))) * H
            for L in legendas:
                if L["ini"] <= tg < L["fim"]:
                    im = render_bloco_legenda(tuple(L["palavras"]))
                    tt = tg - L["ini"]
                    s = 0.78 + 0.22 * ease_out_back(tt / 0.14) if tt < 0.14 else 1.0
                    ylg = float(c.get("legenda_y", R.get("legenda_y", 0.70))) * H
                    if fb is not None:
                        ylg = H * 0.5
                    colar(frame, im, W / 2, ylg, s)
                    break
            if marca is not None:
                if "marca_y" in R:
                    ym = H * float(R["marca_y"])
                else:
                    ym = ylg_atual + 100          # sempre abaixo da legenda, sem encostar
                    if ym > H * 0.82:
                        ym = ylg_atual - 100
                colar(frame, marca, W / 2, ym, 1.0)
            if limpo is not None:
                ultimo_frame = limpo
            if args.previa:
                if k == n // 2:
                    pth = os.path.join(base_dir, "previa", f"cena_{i + 1:02d}.jpg")
                    frame.convert("RGB").resize((360, 640)).save(pth, quality=85)
                    previas.append(pth)
            else:
                enc.stdin.write(frame.convert("RGB").tobytes())
            if args.previa and k > n // 2:
                break
        fa.fechar()
        if fb:
            fb.fechar()
        frame_global += n
        print(f"  cena {i + 1}/{len(cenas)} pronta", flush=True)

    if args.previa:
        imgs = [Image.open(p) for p in previas]
        cols = min(6, len(imgs))
        rows = math.ceil(len(imgs) / cols)
        folha = Image.new("RGB", (cols * 360, rows * 640), (0, 0, 0))
        for j, im in enumerate(imgs):
            folha.paste(im, ((j % cols) * 360, (j // cols) * 640))
        out = os.path.join(base_dir, "previa", "folha_previa.jpg")
        folha.save(out, quality=85)
        print("Prévia:", out)
        return

    enc.stdin.close()
    if enc.wait():
        raise RuntimeError("Falha no encoder do Kit GTA 6.")

    # mixa narração + música de fundo (baixinha, abaixa sozinha quando a voz fala) + efeitos sonoros
    sfx_dir = os.path.join(KIT, "assets", "sfx")
    if not R.get("efeitos_sonoros", True):
        sfx = []
    dur_video = n_total / FPS if not args.ate else min(n_total / FPS, args.ate)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", tmp_video, "-i", audio]
    filtros = ["[1:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[voz][voz_sc]"]
    rotulos = ["[voz]"]
    idx = 2
    musica = escolher_musica(R)
    if musica:
        ganho = float(R.get("volume_musica_db", -33.0)) - volume_medio(musica)
        ini_m = float(R.get("musica_inicio", 0))
        cmd += ["-stream_loop", "-1", "-ss", f"{ini_m:.2f}", "-i", musica]
        filtros.append(
            f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={ganho:.1f}dB,"
            f"atrim=0:{dur_video:.2f},afade=t=in:d=0.6,afade=t=out:st={max(0, dur_video - 1.6):.2f}:d=1.6[m0];"
            f"[m0][voz_sc]sidechaincompress=threshold=0.02:ratio=4:attack=30:release=450:makeup=1[mus]")
        rotulos.append("[mus]")
        idx += 1
        print("Música de fundo:", os.path.basename(musica))
    else:
        filtros[0] = "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[voz]"
    for j, (nome, quando, vol, dmax) in enumerate(sfx):
        cmd += ["-i", os.path.join(sfx_dir, nome + ".wav")]
        ms = int(quando * 1000)
        corte = f"atrim=0:{dmax:.2f},afade=t=out:st={max(0, dmax - 0.15):.2f}:d=0.15," if dmax else ""
        filtros.append(f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,{corte}"
                       f"volume={vol * float(R.get('volume_efeitos', 1.0)):.2f},adelay={ms}|{ms}[s{j}]")
        rotulos.append(f"[s{j}]")
        idx += 1
    if len(rotulos) > 1:
        filtros.append("".join(rotulos) + f"amix=inputs={len(rotulos)}:normalize=0:duration=first[a]")
    else:
        filtros.append("[voz]anull[a]")
    cmd += ["-filter_complex", ";".join(filtros), "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart"]
    if args.ate:
        cmd += ["-t", f"{args.ate:.2f}"]
    cmd += [saida]
    subprocess.run(cmd, check=True)
    os.remove(tmp_video)
    print("\nVídeo pronto:", saida)


if __name__ == "__main__":
    main()
