import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

fig, ax = plt.subplots(figsize=(22, 10), facecolor='white')
ax.set_facecolor('white')
ax.set_xlim(0, 220)
ax.set_ylim(0, 100)
ax.set_aspect('equal')
ax.axis('off')

# Параметры (в единицах чертежа)
yc = 50          # ось
sc = 1.2         # масштаб

L_PR  = 50 * sc
L_mid = 85 * sc
L_NE  = 14 * sc
r     = 22.5 * sc   # Ø45 / 2
rh    = 16   * sc   # Ø32 / 2
ch    = 5           # фаска

x0 = 20
x1 = x0 + L_PR
x2 = x1 + L_mid
x3 = x2 + L_NE

LW = 2.5

def L(xa, ya, xb, yb, lw=LW, c='black', ls='-'):
    ax.plot([xa,xb],[ya,yb], color=c, lw=lw, ls=ls,
            solid_capstyle='butt', solid_joinstyle='miter')

# ── Контур ────────────────────────────────────────────────────────────────────
L(x0, yc+r,    x1,    yc+r)           # ПР верх
L(x0, yc-r,    x1,    yc-r)           # ПР низ
L(x0, yc-r,    x0,    yc+r)           # ПР торец

L(x1, yc+r,    x1+ch, yc+rh)         # фаска верх
L(x1, yc-r,    x1+ch, yc-rh)         # фаска низ

L(x1+ch, yc+rh, x2-ch, yc+rh)        # ручка верх
L(x1+ch, yc-rh, x2-ch, yc-rh)        # ручка низ

L(x2-ch, yc+rh, x2,    yc+r)         # фаска верх
L(x2-ch, yc-rh, x2,    yc-r)         # фаска низ

L(x2, yc+r,    x3,    yc+r)           # НЕ верх
L(x2, yc-r,    x3,    yc-r)           # НЕ низ
L(x3, yc-r,    x3,    yc+r)           # НЕ торец

# ── Осевая ────────────────────────────────────────────────────────────────────
ax.plot([x0-8, x3+8], [yc, yc],
        color='black', lw=1.0, ls=(0,(10,3,2,3)))

# ── Размерные линии (только линии, без текста) ────────────────────────────────
def hdim(xa, xb, y):
    ax.annotate('', xy=(xb,y), xytext=(xa,y),
        arrowprops=dict(arrowstyle='<->', color='black', lw=1.2, mutation_scale=11))
    # выносные
    ax.plot([xa, xa],[yc-r-1, y+1], color='black', lw=0.9)
    ax.plot([xb, xb],[yc-r-1, y+1], color='black', lw=0.9)

def vdim(x, ya, yb):
    ax.annotate('', xy=(x,yb), xytext=(x,ya),
        arrowprops=dict(arrowstyle='<->', color='black', lw=1.2, mutation_scale=11))

# Горизонтальные размеры
hdim(x0,    x1,    yc-r-10)   # 50
hdim(x2,    x3,    yc-r-10)   # 14
hdim(x0,    x3,    yc-r-22)   # 149

# Ø ПР (вертикаль слева)
vdim(x0-12, yc-r, yc+r)
# Ø НЕ (вертикаль справа)
vdim(x3+12, yc-r, yc+r)
# Ø ручки (вертикаль над серединой)
xm = (x1+ch+x2-ch)/2
ax.annotate('', xy=(xm, yc+rh+14), xytext=(xm, yc+rh),
    arrowprops=dict(arrowstyle='->', color='black', lw=1.2, mutation_scale=11))
ax.plot([x1+ch, xm],[yc+rh, yc+rh], color='black', lw=0.9)
ax.plot([x2-ch, xm],[yc+rh, yc+rh], color='black', lw=0.9)

# ── Подписи: только самые важные, КРУПНО ──────────────────────────────────────
fs = 14

# Длины
ax.text((x0+x1)/2, yc-r-14, '50',  ha='center', va='top', fontsize=fs)
ax.text((x2+x3)/2, yc-r-14, '14',  ha='center', va='top', fontsize=fs)
ax.text((x0+x3)/2, yc-r-26, '149', ha='center', va='top', fontsize=fs, fontweight='bold')

# Диаметры
ax.text(x0-14, yc+r+3, 'Ø45.003\n+0.004', ha='center', va='bottom', fontsize=fs-1)
ax.text(x3+14, yc+r+3, 'Ø45.025\n+0.004', ha='center', va='bottom', fontsize=fs-1)
ax.text(xm,    yc+rh+18, 'Ø32',            ha='center', va='bottom', fontsize=fs)

# ПР / НЕ
ax.text((x0+x1)/2, yc+r+6, 'ПР', ha='center', va='bottom',
        fontsize=18, fontweight='bold', color='#1a5276')
ax.text((x2+x3)/2, yc+r+6, 'НЕ', ha='center', va='bottom',
        fontsize=18, fontweight='bold', color='#922b21')

# ── Рамка ─────────────────────────────────────────────────────────────────────
rect = patches.Rectangle((1,1), 218, 98, lw=2, edgecolor='black', facecolor='none')
ax.add_patch(rect)

plt.tight_layout(pad=0.3)
plt.savefig('/Users/liudmila/Проект "Нормирование"/Калибр_Ø45H7.png',
            dpi=220, bbox_inches='tight', facecolor='white')
print("Готово")
