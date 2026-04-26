import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# ─── ПАРАМЕТРЫ КАЛИБРА ───────────────────────────────────────────────────────
nominal = 45          # номинальный диаметр, мм
field = "H7"          # поле допуска отверстия

# Допуски для Ø45 H7 (ГОСТ 25346, IT7 = 25 мкм, нижнее откл. = 0)
D_min = 45.000
D_max = 45.025

# Допуски на калибр (ГОСТ 24853-81, диапазон 30–50 мм, квалитет 7)
H  = 0.004   # допуск на изготовление калибра
Y  = 0.003   # допуск на износ ПР
Z  = 0.003   # смещение поля калибра ПР от D_min

# ПР: от D_min+Z-H/2 до D_min+Z+H/2 (не менее D_min-Y при износе)
D_PR_lo = D_min + Z - H/2   # 45.001
D_PR_hi = D_min + Z + H/2   # 45.005
D_PR_worn = D_min - Y        # 44.997

# НЕ: от D_max до D_max+H
D_NE_lo = D_max              # 45.025
D_NE_hi = D_max + H          # 45.029

# ─── ГАБАРИТЫ КАЛИБРА (ГОСТ 14810-69, Таблица 1, Ø свыше 40 до 50 мм) ───────
L_PR     = 50   # длина ПР-части, мм
L_handle = 85   # длина ручки, мм
L_NE     = 14   # длина НЕ-части, мм
D_gag    = 45.0 # рабочий диаметр (оба конца одинаковый Ø, разные допуски)
D_handle = 32   # диаметр ручки, мм

# ─── РИСУНОК ─────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(18, 11), facecolor='white')

# Основная область чертежа
ax = fig.add_axes([0.02, 0.18, 0.96, 0.78])
ax.set_facecolor('white')

scale = 1.4          # масштаб 1:2 × 1.4 (для читаемости)
W = 380; Hh = 180
ax.set_xlim(0, W)
ax.set_ylim(0, Hh)
ax.set_aspect('equal')
ax.axis('off')

# Производные в единицах чертежа
l_PR     = L_PR     * scale
l_handle = L_handle * scale
l_NE     = L_NE     * scale
r_gag    = D_gag    * scale / 2
r_handle = D_handle * scale / 2

yc = 110          # центральная ось Y
x0 = 25           # начало ПР

x1 = x0 + l_PR          # конец ПР = начало ручки
x2 = x1 + l_handle      # конец ручки = начало НЕ
x3 = x2 + l_NE          # конец НЕ

lw  = 1.6   # основная линия
lw2 = 0.8   # тонкая линия

def line(ax, x1, y1, x2, y2, lw=1.6, color='black', ls='-'):
    ax.plot([x1, x2], [y1, y2], color=color, lw=lw, linestyle=ls, solid_capstyle='butt')

# ── ПР-конец ──
line(ax, x0, yc + r_gag, x1, yc + r_gag)            # верхняя образующая
line(ax, x0, yc - r_gag, x1, yc - r_gag)            # нижняя образующая
line(ax, x0, yc - r_gag, x0, yc + r_gag)            # торец

# Переход ПР → ручка (фаска 45°, 3мм)
ch = 3 * scale
line(ax, x1, yc + r_gag, x1 + ch, yc + r_handle)
line(ax, x1, yc - r_gag, x1 + ch, yc - r_handle)

# ── Ручка ──
line(ax, x1 + ch, yc + r_handle, x2 - ch, yc + r_handle)
line(ax, x1 + ch, yc - r_handle, x2 - ch, yc - r_handle)

# Переход ручка → НЕ (фаска 45°)
line(ax, x2 - ch, yc + r_handle, x2, yc + r_gag)
line(ax, x2 - ch, yc - r_handle, x2, yc - r_gag)

# ── НЕ-конец ──
line(ax, x2, yc + r_gag, x3, yc + r_gag)
line(ax, x2, yc - r_gag, x3, yc - r_gag)
line(ax, x3, yc - r_gag, x3, yc + r_gag)            # торец

# ── Рифление на ручке ──
x_kr0 = x1 + ch + 10
x_kr1 = x2 - ch - 10
n = 18
for i in range(n + 1):
    xi = x_kr0 + (x_kr1 - x_kr0) * i / n
    line(ax, xi, yc - r_handle + 1, xi, yc + r_handle - 1, lw=0.4, color='#888888')

# ── Осевая линия (красная штрихпунктир) ──
ax.plot([x0 - 15, x3 + 15], [yc, yc],
        color='red', lw=0.9, linestyle=(0, (12, 3, 2, 3)))

# ── Штриховка (металл) ── через весь профиль короткими линиями
for xi in np.linspace(x0 + 4, x1 - 4, 18):
    ax.plot([xi, xi + 4], [yc - r_gag + 2, yc + r_gag - 2],
            color='#555555', lw=0.35, alpha=0.45)
for xi in np.linspace(x2 + 4, x3 - 3, 8):
    ax.plot([xi, xi + 3], [yc - r_gag + 2, yc + r_gag - 2],
            color='#555555', lw=0.35, alpha=0.45)

# ─── РАЗМЕРНЫЕ ЛИНИИ ─────────────────────────────────────────────────────────
dim_color = 'black'
txt_size  = 7.5
offset_lo = 18   # отступ ниже детали
offset_hi = 18   # отступ выше детали

def dim_line_h(ax, x_a, x_b, y, text, text_above=True):
    """Горизонтальная размерная линия со стрелками."""
    ax.annotate('', xy=(x_b, y), xytext=(x_a, y),
                arrowprops=dict(arrowstyle='<->', color=dim_color,
                                lw=0.9, mutation_scale=7))
    tx = (x_a + x_b) / 2
    ty = y + (3 if text_above else -4.5)
    ax.text(tx, ty, text, ha='center', va='bottom' if text_above else 'top',
            fontsize=txt_size, color=dim_color, fontfamily='DejaVu Sans')

def dim_line_v(ax, x, y_a, y_b, text, side='right'):
    """Вертикальная размерная линия (для диаметра)."""
    ax.annotate('', xy=(x, y_b), xytext=(x, y_a),
                arrowprops=dict(arrowstyle='<->', color=dim_color,
                                lw=0.9, mutation_scale=7))
    tx = x + (4 if side == 'right' else -4)
    ty = (y_a + y_b) / 2
    ax.text(tx, ty, text, ha='left' if side == 'right' else 'right',
            va='center', fontsize=txt_size, color=dim_color,
            fontfamily='DejaVu Sans')

def ext_line(ax, x, y_from, y_to):
    """Выносная линия."""
    line(ax, x, y_from, x, y_to, lw=0.6, color='#333333', ls='--' if False else '-')

# --- L_PR ---
y_dim_lo = yc - r_gag - offset_lo
ext_line(ax, x0, yc - r_gag, y_dim_lo - 2)
ext_line(ax, x1, yc - r_gag, y_dim_lo - 2)
dim_line_h(ax, x0, x1, y_dim_lo, f'{L_PR}', text_above=False)

# --- L_handle ---
y_dim_lo2 = y_dim_lo - 12
ext_line(ax, x1 + ch, yc - r_handle, y_dim_lo2 - 2)
ext_line(ax, x2 - ch, yc - r_handle, y_dim_lo2 - 2)
dim_line_h(ax, x1 + ch, x2 - ch, y_dim_lo2, f'{L_handle - 6:.0f}', text_above=False)

# --- L_NE ---
ext_line(ax, x2, yc - r_gag, y_dim_lo - 2)
ext_line(ax, x3, yc - r_gag, y_dim_lo - 2)
dim_line_h(ax, x2, x3, y_dim_lo, f'{L_NE}', text_above=False)

# --- Общая длина ---
y_dim_total = y_dim_lo - 24
ext_line(ax, x0, yc - r_gag, y_dim_total - 2)
ext_line(ax, x3, yc - r_gag, y_dim_total - 2)
dim_line_h(ax, x0, x3, y_dim_total, f'{L_PR + L_handle + L_NE}', text_above=False)

# --- Ø ПР (слева, вертикальная) ---
x_dim_pr = x0 - 18
ext_line(ax, x0 + 10, yc - r_gag, yc - r_gag)   # не нужна
ax.annotate('', xy=(x_dim_pr, yc + r_gag), xytext=(x_dim_pr, yc - r_gag),
            arrowprops=dict(arrowstyle='<->', color=dim_color, lw=0.9, mutation_scale=7))
ax.text(x_dim_pr - 3, yc,
        f'Ø{D_PR_lo:.3f}\n+{H*1000:.0f} мкм', ha='right', va='center',
        fontsize=7, color=dim_color)
ax.text(x_dim_pr - 3, yc + r_gag + 2, 'ПР', ha='right', va='bottom',
        fontsize=7.5, fontweight='bold', color='#1a5276')

# --- Ø НЕ (справа, вертикальная) ---
x_dim_ne = x3 + 20
ax.annotate('', xy=(x_dim_ne, yc + r_gag), xytext=(x_dim_ne, yc - r_gag),
            arrowprops=dict(arrowstyle='<->', color=dim_color, lw=0.9, mutation_scale=7))
ax.text(x_dim_ne + 3, yc,
        f'Ø{D_NE_lo:.3f}\n+{H*1000:.0f} мкм', ha='left', va='center',
        fontsize=7, color=dim_color)
ax.text(x_dim_ne + 3, yc + r_gag + 2, 'НЕ', ha='left', va='bottom',
        fontsize=7.5, fontweight='bold', color='#922b21')

# --- Ø ручки (над ручкой) ---
xm = (x1 + ch + x2 - ch) / 2
y_hi = yc + r_handle + offset_hi
ext_line(ax, x1 + ch, yc + r_handle, y_hi + 2)
ext_line(ax, x2 - ch, yc + r_handle, y_hi + 2)
ax.annotate('', xy=(x2 - ch, y_hi), xytext=(x1 + ch, y_hi),
            arrowprops=dict(arrowstyle='<->', color=dim_color, lw=0.9, mutation_scale=7))
ax.text(xm, y_hi + 3, f'Ø{D_handle}', ha='center', va='bottom',
        fontsize=txt_size, color=dim_color)

# ─── НАДПИСИ НА ЧЕРТЕЖЕ ──────────────────────────────────────────────────────
# Шероховатость
ax.text(x0 + l_PR / 2, yc + r_gag + 5, '▽▽▽  Ra 0.32', ha='center', va='bottom',
        fontsize=6.5, color='#555')
ax.text(x2 + l_NE / 2, yc + r_gag + 5, '▽▽▽  Ra 0.32', ha='center', va='bottom',
        fontsize=6.5, color='#555')
ax.text(xm, yc + r_handle + 4, '▽  Ra 3.2', ha='center', va='bottom',
        fontsize=6.5, color='#555')

# Технические требования
tech = (
    "Технические требования:\n"
    "1. Материал: сталь ХВГ ГОСТ 5950-2000\n"
    "2. Твёрдость рабочих поверхностей: HRC 58…65\n"
    "3. Твёрдость ручки: HRC 35…45\n"
    f"4. Предельный размер износа ПР: Ø{D_PR_worn:.3f} мм\n"
    "5. Маркировать: «ПР» и «НЕ» на соответствующих торцах\n"
    "6. Покрытие: Хим. Окс. Прм."
)
ax.text(195, 75, tech, ha='left', va='top', fontsize=7.2,
        color='black', fontfamily='DejaVu Sans',
        linespacing=1.6,
        bbox=dict(boxstyle='round,pad=0.4', facecolor='#f8f8f8', edgecolor='#aaa', lw=0.6))

# Масштаб
ax.text(370, Hh - 5, '1:2', ha='right', va='top', fontsize=8,
        color='#333', style='italic')
ax.text(370, Hh - 13, 'Масштаб', ha='right', va='top', fontsize=7, color='#555')

# ─── РАМКА ───────────────────────────────────────────────────────────────────
rect = patches.Rectangle((2, 2), W - 4, Hh - 4,
                           linewidth=1.5, edgecolor='black', facecolor='none')
ax.add_patch(rect)

# ─── УГЛОВОЙ ШТАМП (упрощённый) ──────────────────────────────────────────────
ax_title = fig.add_axes([0.02, 0.01, 0.96, 0.16])
ax_title.set_xlim(0, 100)
ax_title.set_ylim(0, 20)
ax_title.axis('off')
ax_title.set_facecolor('white')

# Рамка штампа
for x, y, w, h, txt, fs, fw in [
    (0,    0, 60, 8,  f'Калибр-пробка двусторонний  Ø{nominal} {field}', 10, 'bold'),
    (60,   0, 20, 8,  'ГОСТ 14810-69', 8, 'normal'),
    (80,   0, 20, 8,  f'КП-{nominal}{field}', 8.5, 'bold'),
    (0,    8, 30, 6,  'Разраб.: ___________', 7, 'normal'),
    (30,   8, 30, 6,  'Провер.: ___________', 7, 'normal'),
    (60,   8, 20, 6,  'Лист 1 / Листов 1',  7, 'normal'),
    (80,   8, 20, 6,  'Завод / КБ',          7, 'normal'),
    (0,   14, 80, 6,  'Сталь ХВГ  ГОСТ 5950-2000', 7.5, 'normal'),
    (80,  14, 20, 6,  '2026-04',             7, 'normal'),
]:
    rect_s = patches.Rectangle((x, y), w, h,
                                linewidth=0.7, edgecolor='black', facecolor='none')
    ax_title.add_patch(rect_s)
    ax_title.text(x + w/2, y + h/2, txt, ha='center', va='center',
                  fontsize=fs, fontweight=fw)

plt.savefig('/Users/liudmila/Проект "Нормирование"/Чертёж_калибр_Ø45H7.png',
            dpi=180, bbox_inches='tight', facecolor='white')
print("Чертёж сохранён: Чертёж_калибр_Ø45H7.png")
