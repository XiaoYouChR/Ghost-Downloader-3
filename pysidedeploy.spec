[app]
# title of your application
title = Ghost Downloader 3
# project directory. the general assumption is that project_dir is the parent directory
# of input_file
project_dir = .
# source file path
input_file = C:\Users\XiaoYouChR\Desktop\Ghost-Downloader-3\main.py
# directory where exec is stored
exec_directory = .
# path to .pyproject project file
project_file = 

[python]
# python path
python_path = C:\Users\XiaoYouChR\PycharmProjects\PyQt-Fluent-Widgets\venv\Scripts\python.exe
# python packages to install
# ordered-set = increase compile time performance of nuitka packaging
# zstandard = provides final executable size optimization
packages = nuitka,ordered_set,zstandard

[qt]
# comma separated path to qml files required
# normally all the qml files are added automatically
qml_files = 

[nuitka]
# (str) specify any extra nuitka arguments
# eg = extra_args = --show-modules --follow-stdlib
extra_args = --quiet --windows-icon-from-ico=./logo.ico --windows-disable-console

