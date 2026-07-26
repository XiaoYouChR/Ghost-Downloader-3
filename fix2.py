import re

path = 'features/ed2k_pack/config.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_import = 'from app.view.components.setting_cards import SelectFolderSettingCard, SpinBoxSettingCard'
new_import = 'from app.view.components.setting_cards import LineEditSettingCard, SelectFolderSettingCard, SpinBoxSettingCard'
content = content.replace(old_import, new_import)

old_cards = '''                SpinBoxSettingCard(
                    FluentIcon.LINK, self.tr("监听端口"),
                    self.tr("0 表示交给系统自动分配可用端口"), "",
                    self.listenPort, group, 1,
                ),
            ])'''

new_cards = '''                SpinBoxSettingCard(
                    FluentIcon.LINK, self.tr("监听端口"),
                    self.tr("0 表示交给系统自动分配可用端口"), "",
                    self.listenPort, group, 1,
                ),
                LineEditSettingCard(
                    FluentIcon.GLOBE, self.tr("Server List URL"),
                    self.tr("URL of server.met for eD2k server bootstrap"),
                    self.serverMetSource, group, placeholder="http://upd.emule-security.org/server.met",
                ),
                LineEditSettingCard(
                    FluentIcon.LINK, self.tr("KAD Nodes URL"),
                    self.tr("URL of nodes.dat for KAD network bootstrap"),
                    self.nodesDatSource, group, placeholder="http://upd.emule-security.org/nodes.dat",
                ),
            ])'''

content = content.replace(old_cards, new_cards)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
