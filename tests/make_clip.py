"""Builds a synthetic 20 s test clip: normal slides, with a GitHub URL on screen for only 0.3 s (7.4-7.7 s)."""
import os, subprocess, sys
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H, FPS = 1280, 720, 30


def slide(lines, size=64):
    img = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, size)
    y = 200
    for ln in lines:
        d.text((80, y), ln, fill=(10, 10, 10), font=f)
        y += size + 30
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def build(out_mp4, url="github.com/onyx-dot-app/onyx", flash=(7.4, 7.7)):
    raw = out_mp4 + ".raw.avi"
    vw = cv2.VideoWriter(raw, cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
    s_a = slide(["Install these", "10 GitHub repos"])
    s_b = slide(["Top tool for", "enterprise search"])
    s_url = slide(["Repo link:", url], size=56)
    s_c = slide(["Comment REPOS", "to get the list"])
    s_d = slide(["Follow for more"])
    for n in range(int(20 * FPS)):
        t = n / FPS
        if t < 6: f = s_a
        elif t < flash[0]: f = s_b
        elif t < flash[1]: f = s_url
        elif t < 14: f = s_c
        else: f = s_d
        vw.write(f)
    vw.release()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-c:v", "libx264", "-crf", "30", "-pix_fmt", "yuv420p", out_mp4], check=True)
    os.remove(raw)
    return out_mp4


if __name__ == "__main__":
    print(build(sys.argv[1]))
