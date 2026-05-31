import re

class QtMarkdownRender:
    
    @classmethod
    def render(cls, markdown_text: str) -> str:
        if not markdown_text:
            return ""

        text = markdown_text
        
        # 定义简单的文本和 Emoji 替换（注意结尾加上两个空格和换行符，确保 Markdown 换行）
        alerts = {
            "[!NOTE]": "**ℹ️ 提示 (NOTE)**  \n",
            "[!TIP]": "**💡 技巧 (TIP)**  \n",
            "[!IMPORTANT]": "**✨ 重要 (IMPORTANT)**  \n",
            "[!WARNING]": "**⚠️ 警告 (WARNING)**  \n",
            "[!CAUTION]": "**🚨 危险 (CAUTION)**  \n"
        }
        
        # 遍历替换
        for gh_tag, qt_tag in alerts.items():
            text = text.replace(gh_tag, qt_tag)
            
        # 清理一下 GitHub 警告块特有的引用符号 '>'
        # 这样 Qt 渲染出来的格式最干净
        text = re.sub(r"^[ \t]*>[ \t]?", "", text, flags=re.MULTILINE)
        
        return text