"""
安装脚本：将编译后的程序复制到指定目录并创建快捷方式
"""
import shutil
import sys
import subprocess
from pathlib import Path
import win32com.client


# ==================== 配置区域 ====================
# 源目录配置（编译后的程序所在目录，None 表示使用脚本所在目录）
SOURCE_BASE_DIR = None  # 例如: r"D:\Tools\.PyTools\PyHostsFileEdit\src\HostsfileEdit"
SOURCE_DIST_FOLDER = "dist/Ghost Downloader.dist"  # 相对于 SOURCE_BASE_DIR 的路径

# 安装目标目录（程序将被直接复制到此目录）
INSTALL_BASE_DIR = r"D:\Tools\Ghost Downloader"

# 可执行文件名
EXE_NAME = "Ghost Downloader.exe"

# 快捷方式名称（不含 .lnk 后缀）
SHORTCUT_NAME = "Ghost Downloader"

# 快捷方式描述
SHORTCUT_DESCRIPTION = "桌面快捷方式"

# 是否创建桌面快捷方式
CREATE_DESKTOP_SHORTCUT = False

# 是否添加到开始菜单
CREATE_START_MENU_SHORTCUT = True
# =================================================


def get_desktop_path():
    """获取真实的桌面路径（支持用户自定义桌面位置）"""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        # 使用 Shell 对象获取桌面特殊文件夹路径
        desktop_path = shell.SpecialFolders("Desktop")
        return Path(desktop_path)
    except Exception as e:
        print(f"警告: 无法获取桌面路径，使用默认路径: {e}")
        # 降级方案：使用默认路径
        return Path.home() / "Desktop"


def create_shortcut(target_path, shortcut_path, description=""):
    """创建 Windows 快捷方式"""
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.WorkingDirectory = str(target_path.parent)
    shortcut.Description = description
    shortcut.IconLocation = str(target_path)
    shortcut.save()


def install_program():
    """安装程序到指定目录"""

    # 确定源基础目录
    if SOURCE_BASE_DIR is None:
        # 使用脚本所在目录
        source_base = Path(__file__).parent.absolute()
    else:
        # 使用配置的目录
        source_base = Path(SOURCE_BASE_DIR)

    # 源目录：编译后的程序文件夹
    source_dir = source_base / SOURCE_DIST_FOLDER

    # 使用配置的目标目录（直接安装到此目录）
    target_dir = Path(INSTALL_BASE_DIR)

    # 使用配置的可执行文件名
    exe_name = EXE_NAME

    print("=" * 60)
    print(f"开始安装 {EXE_NAME}")
    print("=" * 60)

    # 检查源目录是否存在
    if not source_dir.exists():
        print(f"错误: 找不到编译后的程序目录")
        print(f"请先运行 build.py 进行编译")
        print(f"期望目录: {source_dir}")
        sys.exit(1)

    # 检查可执行文件是否存在
    source_exe = source_dir / exe_name
    if not source_exe.exists():
        print(f"错误: 找不到可执行文件 {exe_name}")
        print(f"期望路径: {source_exe}")
        sys.exit(1)

    print(f"源目录: {source_dir}")
    print(f"目标目录: {target_dir}")
    print("=" * 60)

    try:
        # 创建目标目录（如果不存在）
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n✓ 创建目标目录: {target_dir}")

        # 如果目标目录已存在内容，先清空（保留目录本身）
        if target_dir.exists():
            print(f"✓ 清空目标目录...")
            for item in target_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        # 复制 SOURCE_DIST_FOLDER 内的所有文件到目标目录
        print(f"✓ 复制程序文件...")
        for item in source_dir.iterdir():
            if item.is_dir():
                shutil.copytree(item, target_dir / item.name)
            else:
                shutil.copy2(item, target_dir / item.name)
        print(f"  已复制到: {target_dir}")

        # 目标可执行文件路径
        target_exe = target_dir / exe_name

        # 创建快捷方式
        shortcuts_created = []
        
        # 创建桌面快捷方式
        if CREATE_DESKTOP_SHORTCUT:
            desktop_path = get_desktop_path()
            desktop_shortcut = desktop_path / f"{SHORTCUT_NAME}.lnk"
            print(f"\n✓ 创建桌面快捷方式...")
            create_shortcut(
                target_exe,
                desktop_shortcut,
                description=SHORTCUT_DESCRIPTION
            )
            print(f"  桌面快捷方式: {desktop_shortcut}")
            shortcuts_created.append(("桌面", desktop_shortcut))
        
        # 添加到开始菜单
        if CREATE_START_MENU_SHORTCUT:
            start_menu_path = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            start_menu_shortcut = start_menu_path / f"{SHORTCUT_NAME}.lnk"
            print(f"\n✓ 添加到开始菜单...")
            create_shortcut(
                target_exe,
                start_menu_shortcut,
                description=SHORTCUT_DESCRIPTION
            )
            print(f"  开始菜单快捷方式: {start_menu_shortcut}")
            shortcuts_created.append(("开始菜单", start_menu_shortcut))

        print("\n" + "=" * 60)
        print("安装成功！")
        print("=" * 60)
        print(f"程序目录: {target_dir}")
        print(f"可执行文件: {target_exe}")
        
        if shortcuts_created:
            print("\n已创建的快捷方式:")
            for idx, (location, path) in enumerate(shortcuts_created, 1):
                print(f"{idx}. {location}: {path}")
        
        print("\n可以通过以下方式启动程序:")
        if shortcuts_created:
            for idx, (location, path) in enumerate(shortcuts_created, 1):
                print(f"{idx}. 双击{location}快捷方式")
            print(f"{len(shortcuts_created) + 1}. 直接运行: {target_exe}")
        else:
            print(f"1. 直接运行: {target_exe}")
        print("=" * 60)

        return 0

    except PermissionError as e:
        print("\n" + "=" * 60)
        print(f"错误: 权限不足")
        print(f"详情: {str(e)}")
        print("请以管理员身份运行此脚本")
        print("=" * 60)
        return 1

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"安装失败: {str(e)}")
        print("=" * 60)
        return 1


def check_and_install_pywin32():
    """检查是否安装了 pywin32，如果没有则自动安装"""
    print("检查 pywin32 是否已安装...")
    try:
        # 检查 pywin32 是否已安装
        import win32com.client
        print("✓ pywin32 已安装")
        return True
    except ImportError:
        print("✗ 未安装 pywin32")
        print("正在自动安装 pywin32...")

        try:
            # 自动安装 pywin32
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "pywin32"],
                check=True
            )
            print("✓ pywin32 安装成功")
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ pywin32 安装失败: {e}")
            print("请手动运行: pip install pywin32")
            return False


if __name__ == "__main__":
    # 检查并安装 pywin32
    if not check_and_install_pywin32():
        sys.exit(1)

    # 执行安装
    exit_code = install_program()
    sys.exit(exit_code)
