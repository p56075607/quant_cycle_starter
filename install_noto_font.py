#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""下載並安裝 Noto Serif CJK JP 字體"""

import os
import sys
import urllib.request
import shutil
from pathlib import Path

print("=" * 70)
print("Noto Serif CJK JP 字體安裝程式")
print("=" * 70)

# 字體下載連結
FONTS = {
    "NotoSerifCJKjp-Regular.otf": "https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/Japanese/NotoSerifCJKjp-Regular.otf",
    "NotoSerifCJKjp-Bold.otf": "https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/Japanese/NotoSerifCJKjp-Bold.otf",
}

# Windows 用戶字體目錄
user_fonts_dir = Path(os.environ['LOCALAPPDATA']) / 'Microsoft' / 'Windows' / 'Fonts'
user_fonts_dir.mkdir(parents=True, exist_ok=True)

print(f"\n字體安裝目錄: {user_fonts_dir}\n")

# 下載並安裝字體
for font_name, url in FONTS.items():
    dest_path = user_fonts_dir / font_name
    
    if dest_path.exists():
        print(f"[已存在] {font_name}")
        continue
    
    try:
        print(f"[下載中] {font_name}...")
        temp_path = Path(os.environ['TEMP']) / font_name
        urllib.request.urlretrieve(url, temp_path)
        
        print(f"[安裝中] {font_name}...")
        shutil.copy2(temp_path, dest_path)
        
        # 註冊字體到 Windows Registry（需要管理員權限，這裡我們用用戶級安裝）
        try:
            import winreg
            registry_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path, 0, winreg.KEY_SET_VALUE)
            
            # 字體註冊名稱
            font_registry_name = font_name.replace('.otf', ' (TrueType)')
            winreg.SetValueEx(key, font_registry_name, 0, winreg.REG_SZ, str(dest_path))
            winreg.CloseKey(key)
            print(f"[已註冊] {font_name}")
        except Exception as e:
            print(f"[警告] 無法註冊字體到註冊表: {e}")
        
        print(f"[完成] {font_name}\n")
        
    except Exception as e:
        print(f"[錯誤] 安裝 {font_name} 失敗: {e}\n")

print("\n" + "=" * 70)
print("字體安裝完成！")
print("\n重要提示:")
print("1. 需要重啟所有 Python 程式（包括 Jupyter、IDE 等）")
print("2. 可能需要清除 matplotlib 快取")
print("3. 如果仍然無法使用，可能需要重啟電腦")
print("=" * 70)

# 驗證安裝
print("\n驗證字體安裝:")
installed_fonts = list(user_fonts_dir.glob("NotoSerif*"))
if installed_fonts:
    print(f"找到 {len(installed_fonts)} 個 Noto Serif 字體:")
    for font in installed_fonts:
        print(f"  - {font.name}")
else:
    print("未找到已安裝的 Noto Serif 字體")

