"""
使用 Nuitka 编译项目
配置：非独立模式、并行编译、加速编译
"""
import subprocess
import sys
import os
import argparse
import shutil
from pathlib import Path

# ==================== 配置参数 ====================
# 文件路径配置
MAIN_FILE_NAME = r"Ghost-Downloader-3.py"              # 主文件名
ICON_FILE_NAME = r"resources\logo.png"             # 图标文件名
OUTPUT_DIR_NAME = r"dist"                # 输出目录名

# 输出文件配置
OUTPUT_FILENAME = "Ghost Downloader.exe"  # 输出可执行文件名

# 编译模式配置
USE_STANDALONE = True                   # 是否使用 standalone 模式（打包所有依赖）
USE_ONEFILE = False                     # 是否使用 onefile 模式（单文件）
DISABLE_CONSOLE = True                  # 是否禁用控制台窗口

# 编译优化配置
PARALLEL_JOBS = 32                      # 并行编译进程数
ENABLE_LTO = False                      # 是否启用链接时优化（LTO）
REMOVE_BUILD_DIR = True                 # 编译成功后是否删除构建目录

# 插件配置
ENABLE_PYSIDE6_PLUGIN = True            # 是否启用 PySide6 插件

# 显示配置
SHOW_PROGRESS = True                    # 是否显示编译进度
SHOW_MEMORY = True                      # 是否显示内存使用

# 依赖文件复制配置
COPY_DEPENDENCIES = True                # 是否复制依赖文件
DEPENDENCY_FOLDERS = []  # 需要复制的文件夹列表
DEPENDENCY_FILES = []   # 需要复制的文件列表
# ==================================================


def copy_dependencies(output_dist_dir):
    """复制依赖文件到编译输出目录"""
    if not COPY_DEPENDENCIES:
        return

    current_dir = Path(__file__).parent.absolute()

    print("\n" + "=" * 60)
    print("开始复制依赖文件")
    print("=" * 60)

    # 复制文件夹
    for folder_name in DEPENDENCY_FOLDERS:
        source_folder = current_dir / folder_name
        target_folder = output_dist_dir / folder_name

        if source_folder.exists():
            try:
                # 如果目标文件夹已存在，先删除
                if target_folder.exists():
                    shutil.rmtree(target_folder)

                # 复制整个文件夹
                shutil.copytree(source_folder, target_folder)
                print(f"✓ 已复制文件夹: {folder_name}")
            except Exception as e:
                print(f"✗ 复制文件夹 {folder_name} 失败: {e}")
        else:
            print(f"⚠ 文件夹不存在，跳过: {folder_name}")

    # 复制单个文件
    for file_name in DEPENDENCY_FILES:
        source_file = current_dir / file_name
        target_file = output_dist_dir / file_name

        if source_file.exists():
            try:
                shutil.copy2(source_file, target_file)
                print(f"✓ 已复制文件: {file_name}")
            except Exception as e:
                print(f"✗ 复制文件 {file_name} 失败: {e}")
        else:
            print(f"⚠ 文件不存在，跳过: {file_name}")

    print("=" * 60)


def build_with_nuitka():
    """使用 Nuitka 编译项目"""

    # 获取当前脚本所在目录
    current_dir = Path(__file__).parent.absolute()

    # 主文件路径
    main_file = current_dir / MAIN_FILE_NAME

    # 图标路径
    icon_file = current_dir / ICON_FILE_NAME

    # 输出目录 - dist 文件夹
    output_dir = current_dir / OUTPUT_DIR_NAME

    # 创建 dist 目录（如果不存在）
    output_dir.mkdir(exist_ok=True)

    # 检查文件是否存在
    if not main_file.exists():
        print(f"错误: 找不到主文件 {main_file}")
        sys.exit(1)

    if not icon_file.exists():
        print(f"警告: 找不到图标文件 {icon_file}")

    print("=" * 60)
    print("开始使用 Nuitka 编译项目")
    print("=" * 60)
    print(f"主文件: {main_file}")
    print(f"图标文件: {icon_file}")
    print(f"输出目录: {output_dir}")
    print("=" * 60)

    # Nuitka 编译命令参数
    nuitka_args = [
        sys.executable,
        "-m", "nuitka",

        # 基本设置
        str(main_file),

        # 输出设置
        f"--output-dir={output_dir}",
        f"--output-filename={OUTPUT_FILENAME}",

        # 图标设置
        f"--windows-icon-from-ico={icon_file}",

        # 自动下载依赖
        "--assume-yes-for-downloads",
    ]

    # 根据配置添加编译模式参数
    if USE_STANDALONE:
        nuitka_args.append("--standalone")  # 打包 Python 运行时和所有依赖到文件夹

    if USE_ONEFILE:
        nuitka_args.append("--onefile")  # 打包成单个可执行文件

    # Windows 特定设置
    if DISABLE_CONSOLE:
        nuitka_args.append("--windows-console-mode=disable")  # 禁用控制台窗口

    # 插件配置
    if ENABLE_PYSIDE6_PLUGIN:
        nuitka_args.append("--enable-plugin=pyside6")  # 启用 PySide6 插件

    # 编译优化
    nuitka_args.append(f"--jobs={PARALLEL_JOBS}")  # 并行编译

    if not ENABLE_LTO:
        nuitka_args.append("--lto=no")  # 禁用链接时优化（LTO），加快编译速度

    if REMOVE_BUILD_DIR:
        nuitka_args.append("--remove-output")  # 编译成功后删除构建目录

    # 显示设置
    if SHOW_PROGRESS:
        nuitka_args.append("--show-progress")

    if SHOW_MEMORY:
        nuitka_args.append("--show-memory")

    print("\n执行命令:")
    print(" ".join(nuitka_args))
    print("\n" + "=" * 60)

    try:
        # 执行编译
        result = subprocess.run(
            nuitka_args,
            cwd=current_dir,
            check=True,
            text=True
        )

        print("\n" + "=" * 60)
        print("编译成功！")
        output_dist_dir = output_dir / 'main.dist'
        print(f"程序文件夹: {output_dist_dir}")
        print(f"可执行文件: {output_dist_dir / OUTPUT_FILENAME}")
        print("=" * 60)

        # 复制依赖文件
        copy_dependencies(output_dist_dir)

        print("\n" + "=" * 60)
        print("构建完成！")
        print("\n说明: 已打包所有依赖，可将 dist 文件夹复制到其他电脑运行")
        print("=" * 60)

        return 0

    except subprocess.CalledProcessError as e:
        print("\n" + "=" * 60)
        print(f"编译失败，错误码: {e.returncode}")
        print("=" * 60)
        return e.returncode

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"发生错误: {str(e)}")
        print("=" * 60)
        return 1


def clean_build_files():
    """清理编译生成的文件"""
    current_dir = Path(__file__).parent.absolute()
    output_dir = current_dir / OUTPUT_DIR_NAME

    print("=" * 60)
    print("开始清理编译文件")
    print("=" * 60)

    if not output_dir.exists():
        print(f"输出目录不存在: {output_dir}")
        print("无需清理")
        print("=" * 60)
        return 0

    try:
        # 删除整个 dist 目录
        shutil.rmtree(output_dir)
        print(f"✓ 已删除: {output_dir}")
        print("=" * 60)
        print("清理完成！")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"✗ 清理失败: {str(e)}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="使用 Nuitka 编译项目或清理编译文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python build.py          # 编译项目
  python build.py build    # 编译项目
  python build.py clean    # 清理编译文件
        """
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="build",
        choices=["build", "clean"],
        help="要执行的命令 (默认: build)"
    )

    args = parser.parse_args()

    # 执行对应的命令
    if args.command == "clean":
        exit_code = clean_build_files()
        sys.exit(exit_code)

    # build 命令
    # 检查是否安装了 Nuitka
    try:
        subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError:
        print("错误: 未安装 Nuitka")
        print("请运行: pip install nuitka")
        sys.exit(1)

    # 执行编译
    exit_code = build_with_nuitka()
    sys.exit(exit_code)
