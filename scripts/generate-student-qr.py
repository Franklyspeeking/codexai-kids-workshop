#!/usr/bin/env python3
"""Create a local QR code from an already approved private family share URL."""
import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit

try:
    import qrcode
except ImportError as exc:
    raise SystemExit('请先运行：python3 -m venv scripts/.venv && scripts/.venv/bin/pip install -r scripts/qr-requirements.txt') from exc

parser = argparse.ArgumentParser()
parser.add_argument('url', help='教师后台显示的完整家长分享链接')
parser.add_argument('--output', help='PNG 输出路径')
args = parser.parse_args()
url = args.url.strip()
parts = urlsplit(url)
if parts.scheme != 'https' or parts.netloc != 'codexai.site' or not re.fullmatch(r'/share/[A-Za-z0-9_-]{32,64}/',parts.path) or parts.query or parts.fragment:
    parser.error('请粘贴教师后台生成的 https://codexai.site/share/.../ 家长链接')
output = Path(args.output or 'preparation/二维码/学生作品/家长分享.png')
output.parent.mkdir(parents=True, exist_ok=True)
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
qr.add_data(url)
qr.make(fit=True)
qr.make_image(fill_color='#183e30', back_color='white').save(output)
print(f'{output.resolve()}\n{url}')
