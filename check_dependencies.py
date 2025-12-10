#!/usr/bin/env python3
"""检查所有必需的依赖是否已安装"""

required_packages = {
    'streamlit': 'Streamlit',
    'pandas': 'Pandas',
    'requests': 'Requests',
    'openpyxl': 'OpenPyXL',
    'plotly': 'Plotly'
}

missing_packages = []
installed_packages = []

for package, name in required_packages.items():
    try:
        __import__(package)
        installed_packages.append(name)
        print(f"✅ {name} 已安装")
    except ImportError:
        missing_packages.append(package)
        print(f"❌ {name} 未安装")

print("\n" + "="*50)
if missing_packages:
    print(f"缺少 {len(missing_packages)} 个包: {', '.join(missing_packages)}")
    print("\n请运行以下命令安装:")
    print("  pip install " + " ".join(missing_packages))
    print("\n或使用 requirements.txt:")
    print("  pip install -r requirements.txt")
    exit(1)
else:
    print("✅ 所有必需的库都已安装！")
    print(f"已安装: {', '.join(installed_packages)}")
    exit(0)

