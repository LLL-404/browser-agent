"""Camoufox 快速下载工具 - 支持断点续传和多镜像"""

import os
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "v135.0.1-beta.24"
FILENAME = f"camoufox-135.0.1-beta.24-win.x86_64.zip"
URL = f"https://github.com/daijro/camoufox/releases/download/{VERSION}/{FILENAME}"

MIRRORS = [
    URL,
    f"https://ghproxy.net/{URL}",
    f"https://gh-proxy.com/{URL}",
    f"https://gh.api.030101.xyz/{URL}",
]

TARGET_DIR = Path.home() / ".camoufox" / "browsers"
TARGET_FILE = TARGET_DIR / FILENAME


def download_with_progress(url: str, target: Path) -> bool:
    print(f"📥 正在从: {url[:60]}...")
    
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        mode = 'ab' if target.exists() else 'wb'
        current_size = target.stat().st_size if target.exists() else 0
        
        if current_size > 0:
            req.add_header('Range', f'bytes={current_size}-')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            total = int(response.headers.get('Content-Length', 0))
            
            if response.status == 206:
                content_range = response.headers.get('Content-Range', '')
                if content_range:
                    total = int(content_range.split('/')[-1])
            
            downloaded = current_size
            
            with open(target, mode) as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total > 0:
                        pct = (downloaded / total) * 100
                        mb_downloaded = downloaded / (1024 * 1024)
                        mb_total = total / (1024 * 1024)
                        bar_len = 30
                        filled = int(bar_len * pct / 100)
                        bar = '█' * filled + '░' * (bar_len - filled)
                        print(f"\r  [{bar}] {pct:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", 
                              end='', flush=True)
        
        print(f"\n✅ 下载完成!")
        return True
        
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        return False


def extract_camoufox(zip_path: Path):
    print(f"\n📦 解压中...")
    
    extract_dir = TARGET_DIR / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = zf.namelist()
        total = len(members)
        
        for i, member in enumerate(members):
            zf.extract(member, extract_dir)
            if (i + 1) % 10 == 0 or i == total - 1:
                pct = ((i + 1) / total) * 100
                print(f"\r  解压进度: {pct:.1f}% ({i+1}/{total} 文件)", end='', flush=True)
    
    print(f"\n✅ 解压完成! -> {extract_dir}")
    return extract_dir


def main():
    print("=" * 50)
    print("🦊 Camoufox Firefox 引擎下载器")
    print("=" * 50)
    print(f"版本: {VERSION}")
    print(f"大小: ~530 MB")
    print()
    
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    
    if TARGET_FILE.exists():
        size = TARGET_FILE.stat().st_size / (1024 * 1024)
        print(f"⚠️  发现已有文件 ({size:.1f} MB)")
        
        if size > 500:
            print("✅ 文件可能已完整，跳过下载")
        else:
            print("⚠️  文件不完整，将尝试断点续传")
    
    success = False
    for i, mirror in enumerate(MIRRORS):
        print(f"\n--- 镜像 {i+1}/{len(MIRRORS)} ---")
        if download_with_progress(mirror, TARGET_FILE):
            success = True
            break
        
        if i < len(MIRRORS) - 1:
            print("\n⏭️  尝试下一个镜像...")
    
    if not success:
        print("\n❌ 所有镜像都失败!")
        print("\n手动下载链接:")
        print(URL)
        print(f"\n请下载后放到: {TARGET_FILE}")
        sys.exit(1)
    
    extract_dir = extract_camoufox(TARGET_FILE)
    
    print("\n" + "=" * 50)
    print("🎉 Camoufox 安装完成!")
    print("=" * 50)
    print(f"路径: {extract_dir}")


if __name__ == "__main__":
    main()
