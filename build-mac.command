echo 'Ghost Downloader 构建工具 Mac 版'
echo '输入当前用户密码（开机密码）以继续（Unix 环境下密码默认不显示）'
sudo rm -rf ./dist
pyinstaller main.py --clean -w -i logo.icns -n Ghost-Downloader\ 3 -F --osx-bundle-identifier app.ghost.downloader #--collect-all app --collect-all chrome_extension
cp -R ./plugins ./dist/Ghost-Downloader\ 3.app/Contents/
cp -R ./dist/Ghost-Downloader\ 3.app ./
sudo rm -rf ./build
sudo rm -rf ./dist
sudo rm ./Ghost-Downloader\ 3.spec
echo '构建完成'