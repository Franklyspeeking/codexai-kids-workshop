#!/usr/bin/env python3
"""Create a local PNG QR code for a published, numbered student work."""
import argparse
import re
from pathlib import Path

try:
    import qrcode
except ImportError as exc:
    raise SystemExit('请先运行：python3 -m venv scripts/.venv && scripts/.venv/bin/pip install -r scripts/qr-requirements.txt') from exc

parser = argparse.ArgumentParser()
parser.add_argument('code', help='作品编号，如 s001')
parser.add_argument('--output', help='PNG 输出路径')
args = parser.parse_args()
if not re.fullmatch(r'[a-z][a-z0-9-]{2,30}', args.code):
    parser.error('作品编号格式不正确')
url = f'https://codexai.site/works/{args.code}/money/'
output = Path(args.output or f'preparation/二维码/学生作品/{args.code}.png')
output.parent.mkdir(parents=True, exist_ok=True)
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
qr.add_data(url)
qr.make(fit=True)
qr.make_image(fill_color='#183e30', back_color='white').save(output)
print(f'{output.resolve()}\n{url}')
