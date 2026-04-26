import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

fig = plt.figure(figsize=(20, 12), facecolor='white')

# ─── Основной вид ────────────────────────────────────────────────────────────
ax = fig.add_axes([0.03, 0.22, 0.68, 0.72])
ax.set_facecolor('white')
ax.set_xlim(0, 280)
ax.set_ylim(0, 130)
ax.set_aspect('equal')
ax.axis('off')

# Параметры калибра Ø45 H7
# ГОСТ 24853-81: для d=45мм, IT7=25мкм: H=4, Y=3, Z=3
D_PR  = 45.003   # нижняя граница ПР (D_min + Z - H/2)
D_NE  = 45.025   # нижняя граница НЕ (D_max)
dH    = "+0.004" # допуск калибра

L_PR  = 50
L_NE  = 14
L_tot = 149      # общая длина

sc = 1.35        # масштаб отображения
yc = 72          # ось симметрии
r  = 45/2 * sc   # радиус рабочей части = 30.375
rh = 32/2 * sc   # радиус ручки = 21.6
ch = 4 * sc      # фаска

x0 = 30          # начало ПР
x1 = x0 + L_PR * sc          # конец ПР
x2 = x1 + (L_tot-L_PR-L_NE)*sc  # конец ручки
x3 = x2 + L_NE * sc          # конец НЕ

LW = 2.0   # толщина основных линий

def L(ax, xa, ya, xb, yb, lw=LW, c='black', ls='-'):
    ax.plot([xa,xb],[ya,yb], color=c, lw=lw, ls=ls, solid_capstyle='butt')

# ── Контур калибра (главный вид) ──────────────────────────────────────────────
# ПР
L(ax, x0, yc+r,  x1, yc+r)
L(ax, x0, yc-r,  x1, yc-r)
L(ax, x0, yc-r,  x0, yc+r)          # торец ПР

# фаска ПР→ручка
L(ax, x1, yc+r,  x1+ch, yc+rh)
L(ax, x1, yc-r,  x1+ch, yc-rh)

# Ручка
L(ax, x1+ch, yc+rh, x2-ch, yc+rh)
L(ax, x1+ch, yc-rh, x2-ch, yc-rh)

# фаска ручка→НЕ
L(ax, x2-ch, yc+rh, x2, yc+r)
L(ax, x2-ch, yc-rh, x2, yc-r)

# НЕ
L(ax, x2, yc+r,  x3, yc+r)
L(ax, x2, yc-r,  x3, yc-r)
L(ax, x3, yc-r,  x3, yc+r)          # торец НЕ

# ── Осевая линия ──────────────────────────────────────────────────────────────
ax.plot([x0-10, x3+10], [yc, yc],
        c='black', lw=0.9, ls=(0,(8,2,2,2)))

# ── Линия сечения А–А (на ручке) ─────────────────────────────────────────────
xs = (x1+ch + x2-ch)/2
L(ax, xs, yc+rh+10, xs, yc+rh+2, lw=1.0, c='black')
L(ax, xs, yc-rh-2,  xs, yc-rh-10, lw=1.0, c='black')
ax.text(xs-5, yc+rh+13, 'А', fontsize=10, fontweight='bold', ha='center')
ax.text(xs+5, yc+rh+13, 'А', fontsize=10, fontweight='bold', ha='center')
# стрелки
ax.annotate('', xy=(xs, yc+rh+2), xytext=(xs, yc+rh+10),
            arrowprops=dict(arrowstyle='->', color='black', lw=1.2))
ax.annotate('', xy=(xs, yc-rh-2), xytext=(xs, yc-rh-10),
            arrowprops=dict(arrowstyle='->', color='black', lw=1.2))

# ── Размерные линии ───────────────────────────────────────────────────────────
def hdim(ax, xa, xb, y, text, fontsize=9):
    """Горизонтальный размер."""
    ax.annotate('', xy=(xb,y), xytext=(xa,y),
                arrowprops=dict(arrowstyle='<->', color='black', lw=1.0,
                                mutation_scale=9))
    ax.text((xa+xb)/2, y-4, text, ha='center', va='top', fontsize=fontsize)

def vdim(ax, x, ya, yb, text, side='left', fontsize=9):
    """Вертикальный размер."""
    ax.annotate('', xy=(x,yb), xytext=(x,ya),
                arrowprops=dict(arrowstyle='<->', color='black', lw=1.0,
                                mutation_scale=9))
    ox = -5 if side=='left' else 5
    ax.text(x+ox, (ya+yb)/2, text, ha='right' if side=='left' else 'left',
            va='center', fontsize=fontsize)

def ext(ax, x, y0, y1, lw=0.8):
    L(ax, x, y0, x, y1, lw=lw, c='black')

# Выносные + размер Ø ПР (слева)
xv = x0 - 14
ext(ax, x0+5, yc-r, yc-r)   # не нужна здесь, вертикаль сама
ax.annotate('', xy=(xv,yc+r), xytext=(xv,yc-r),
            arrowprops=dict(arrowstyle='<->', color='black', lw=1.0, mutation_scale=9))
ax.text(xv-3, yc, f'Ø{D_PR:.3f}\n{dH}', ha='right', va='center', fontsize=9,
        linespacing=1.5)

# Выносные + размер Ø НЕ (справа)
xv2 = x3 + 14
ax.annotate('', xy=(xv2,yc+r), xytext=(xv2,yc-r),
            arrowprops=dict(arrowstyle='<->', color='black', lw=1.0, mutation_scale=9))
ax.text(xv2+3, yc, f'Ø{D_NE:.3f}\n{dH}', ha='left', va='center', fontsize=9,
        linespacing=1.5)

# Размер ПР (длина 50) — снизу
y_d1 = yc - r - 14
ext(ax, x0,  yc-r, y_d1-2)
ext(ax, x1,  yc-r, y_d1-2)
hdim(ax, x0, x1, y_d1, '50')

# Размер НЕ (длина 14) — снизу
ext(ax, x2,  yc-r, y_d1-2)
ext(ax, x3,  yc-r, y_d1-2)
hdim(ax, x2, x3, y_d1, '14')

# Размер ручки — снизу ещё ниже
y_d2 = y_d1 - 13
ext(ax, x1+ch, yc-rh, y_d2-2)
ext(ax, x2-ch, yc-rh, y_d2-2)
hdim(ax, x1+ch, x2-ch, y_d2, f'{int((x2-ch-x1-ch)/sc)}')

# Общая длина
y_d3 = y_d2 - 13
ext(ax, x0, yc-r, y_d3-2)
ext(ax, x3, yc-r, y_d3-2)
hdim(ax, x0, x3, y_d3, f'{L_tot}', fontsize=10)

# Ø ручки — сверху
y_u = yc + rh + 14
ext(ax, x1+ch, yc+rh, y_u+2)
ext(ax, x2-ch, yc+rh, y_u+2)
hdim(ax, x1+ch, x2-ch, y_u+6, 'Ø32')

# ── Шероховатость ─────────────────────────────────────────────────────────────
ax.text((x0+x1)/2, yc+r+4,  'Ra 0,08', ha='center', va='bottom', fontsize=8.5,
        fontstyle='italic')
ax.text((x2+x3)/2, yc+r+4,  'Ra 0,08', ha='center', va='bottom', fontsize=8.5,
        fontstyle='italic')
ax.text(xs,        yc-rh-14, 'Ra 1,6',  ha='center', va='top',    fontsize=8.5,
        fontstyle='italic')

# ── Подписи ПР / НЕ ───────────────────────────────────────────────────────────
ax.text((x0+x1)/2, yc+r+14, 'ПРОХОД (ПР)', ha='center', va='bottom',
        fontsize=12, fontweight='bold', color='#1a5276')
ax.text((x2+x3)/2, yc+r+14, 'НЕПРОХОД (НЕ)', ha='center', va='bottom',
        fontsize=12, fontweight='bold', color='#922b21')

# ── Рамка ─────────────────────────────────────────────────────────────────────
rect = patches.Rectangle((1,1), 278, 128, lw=1.8, edgecolor='black', facecolor='none')
ax.add_patch(rect)

# ─── Сечение А–А (справа) ────────────────────────────────────────────────────
ax2 = fig.add_axes([0.72, 0.38, 0.24, 0.56])
ax2.set_facecolor('white')
ax2.set_xlim(-30, 30)
ax2.set_ylim(-30, 38)
ax2.set_aspect('equal')
ax2.axis('off')

# Окружность (ручка Ø32)
circle = plt.Circle((0,0), 16, color='black', fill=False, lw=1.8)
ax2.add_patch(circle)

# Штриховка внутри (металл)
for ang in np.linspace(-80, 80, 12):
    rad = np.radians(ang)
    x_c = 16 * np.cos(rad)
    y_c = 16 * np.sin(rad)
    # хорда для штриховки
    ax2.plot([x_c*0.1, x_c], [y_c*0.1+1.5, y_c],
             color='#555', lw=0.5, alpha=0.5)
# проще — несколько диагональных хорд
for d in np.linspace(-14, 14, 10):
    h = np.sqrt(max(0, 16**2 - d**2))
    ax2.plot([d, d+3], [-h+1, h-1], color='#777', lw=0.4, alpha=0.5)

# Осевые линии сечения
ax2.plot([-20, 20], [0, 0], color='black', lw=0.9, ls=(0,(8,2,2,2)))
ax2.plot([0, 0], [-20, 20], color='black', lw=0.9, ls=(0,(8,2,2,2)))

# Размер диаметра ручки на сечении
ax2.annotate('', xy=(16,24), xytext=(-16,24),
            arrowprops=dict(arrowstyle='<->', color='black', lw=1.0, mutation_scale=9))
ax2.text(0, 27, 'Ø32', ha='center', va='bottom', fontsize=10)

# Рифление (условное обозначение — пунктир по контуру)
circle2 = plt.Circle((0,0), 15, color='gray', fill=False, lw=0.8, ls='--')
ax2.add_patch(circle2)

ax2.text(0, -25, 'Сечение А–А', ha='center', va='top', fontsize=10,
         fontweight='bold')

rect2 = patches.Rectangle((-29,-29), 58, 67, lw=1.5, edgecolor='black', facecolor='none')
ax2.add_patch(rect2)

# ─── Технические требования ───────────────────────────────────────────────────
ax3 = fig.add_axes([0.72, 0.22, 0.24, 0.15])
ax3.set_facecolor('white')
ax3.set_xlim(0, 10)
ax3.set_ylim(0, 10)
ax3.axis('off')

tech = (
    "Технические требования:\n"
    "1. Материал: сталь ХВГ ГОСТ 5950-2000\n"
    "2. Твёрдость рабочих частей: HRC 60…65\n"
    "3. Твёрдость ручки: HRC 35…45\n"
    f"4. Предел износа ПР: Ø{45.000-0.003:.3f} мм\n"
    "5. Покрытие: Хим.Окс.Прм.\n"
    "6. Маркировать «ПР» и «НЕ»"
)
ax3.text(0.5, 9.5, tech, ha='left', va='top', fontsize=7.8, linespacing=1.6)

# ─── Основная надпись (штамп) ─────────────────────────────────────────────────
ax_stamp = fig.add_axes([0.03, 0.01, 0.96, 0.19])
ax_stamp.set_facecolor('white')
ax_stamp.set_xlim(0, 190)
ax_stamp.set_ylim(0, 40)
ax_stamp.axis('off')

cells = [
    # (x, y, w, h, text, fontsize, bold)
    (0,  20, 120, 20, 'Калибр-пробка двусторонний  Ø45 H7',   12, True),
    (120,20, 40,  20, 'ГОСТ 14810-69',                          9, False),
    (160,20, 30,  20, 'КП-45H7',                               10, True),
    (0,  10, 40,  10, 'Разраб.: ________________',              8, False),
    (40, 10, 40,  10, 'Провер.: ________________',              8, False),
    (80, 10, 40,  10, 'Лист 1 / Листов 1',                     8, False),
    (120,10, 40,  10, 'Завод / ОГТ',                           8, False),
    (160,10, 30,  10, '2026-04',                                8, False),
    (0,   0, 100, 10, 'Сталь ХВГ  ГОСТ 5950-2000',             9, False),
    (100, 0, 60,  10, 'Масштаб 1:2',                           8, False),
    (160, 0, 30,  10, 'Лист 1',                                8, False),
]
for x, y, w, h, txt, fs, bold in cells:
    rect = patches.Rectangle((x,y), w, h, lw=0.9, edgecolor='black', facecolor='none')
    ax_stamp.add_patch(rect)
    ax_stamp.text(x+w/2, y+h/2, txt, ha='center', va='center',
                  fontsize=fs, fontweight='bold' if bold else 'normal')

plt.savefig('/Users/liudmila/Проект "Нормирование"/Чертёж_калибр_Ø45H7_v2.png',
            dpi=200, bbox_inches='tight', facecolor='white')
print("Готово: Чертёж_калибр_Ø45H7_v2.png")
