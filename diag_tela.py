try:
    import mss, mss.tools
    with mss.mss() as s:
        for i, m in enumerate(s.monitors):
            print(i, m)
            if i:
                g = s.grab(m)
                mss.tools.to_png(g.rgb, g.size, output=f"monitor{i}.png")
except ImportError:
    print("mss nao instalado")
from PIL import ImageGrab
ImageGrab.grab().save("pillow.png")
print("pillow.png salvo")
