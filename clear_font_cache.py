#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清除 matplotlib 字體快取並重建字體列表"""

import matplotlib as mpl
import matplotlib.font_manager as fm
import os
import glob

print("=" * 60)
print("清除 matplotlib 字體快取")
print("=" * 60)

# 1. 取得快取目錄
cache_dir = mpl.get_cachedir()
print(f"\n1. 快取目錄: {cache_dir}")

# 2. 刪除快取檔案
cache_files = glob.glob(os.path.join(cache_dir, "*.cache"))
cache_files += glob.glob(os.path.join(cache_dir, "fontlist-*.json"))

if cache_files:
    print(f"\n2. 找到 {len(cache_files)} 個快取檔案:")
    for f in cache_files:
        try:
            os.remove(f)
            print(f"   - 已刪除: {os.path.basename(f)}")
        except Exception as e:
            print(f"   - 無法刪除 {os.path.basename(f)}: {e}")
else:
    print("\n2. 沒有找到快取檔案")

# 3. 重建字體列表
print("\n3. 重建字體列表...")
fm._load_fontmanager(try_read_cache=False)
print("   字體列表已重建")

# 4. 檢查 Noto Serif CJK JP 是否可用
print("\n4. 檢查可用的 CJK 字體:")
all_fonts = [f.name for f in fm.fontManager.ttflist]
cjk_fonts = [f for f in all_fonts if 'CJK' in f or 'Noto' in f]

if cjk_fonts:
    print(f"   找到 {len(cjk_fonts)} 個 CJK 相關字體:")
    for font in sorted(set(cjk_fonts)):
        print(f"   - {font}")
else:
    print("   未找到 CJK 字體")

# 5. 檢查 Noto Serif CJK JP 具體狀態
noto_serif_variants = [f.name for f in fm.fontManager.ttflist if 'Noto Serif CJK' in f.name and 'JP' in f.name]
if noto_serif_variants:
    print(f"\n5. Noto Serif CJK JP 字體已安裝:")
    for font in sorted(set(noto_serif_variants)):
        print(f"   ✓ {font}")
else:
    print("\n5. ⚠ Noto Serif CJK JP 字體未找到")
    print("   可能的解決方案:")
    print("   - 確認字體檔案已正確安裝到系統字體目錄")
    print("   - 重啟 Python 程式")
    print("   - 檢查字體檔案名稱是否正確")

print("\n" + "=" * 60)
print("完成！")
print("=" * 60)

