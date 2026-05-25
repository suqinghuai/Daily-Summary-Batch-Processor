import os
import re
import sys
import configparser
import requests

def read_config(config_path):
    """读取配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    
    return {
        'url': config.get('ai', 'url'),
        'api_key': config.get('ai', 'api_key'),
        'model_name': config.get('ai', 'model_name'),
        'temperature': float(config.get('ai', 'temperature')),
        'prompt': config.get('prompt', 'prompt')
    }

def get_md_files(directory='.'):
    """获取目录下所有符合日期格式的md文件"""
    md_files = []
    for filename in os.listdir(directory):
        if filename.endswith('.md') and re.match(r'^\d{4}-\d{2}-\d{2}\.md$', filename):
            md_files.append(os.path.join(directory, filename))
    return md_files

def read_md_file(filepath):
    """读取md文件内容"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def call_ai_api(config, content):
    """调用AI API获取总结"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {config["api_key"]}'
    }
    
    system_prompt = config['prompt'] if config['prompt'].strip() else '请总结这篇日记的内容，用简洁的语言概括主要事件和感受。'
    
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': content}
    ]
    
    data = {
        'model': config['model_name'],
        'messages': messages,
        'temperature': config['temperature']
    }
    
    try:
        response = requests.post(config['url'], headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        
        # 尝试多种可能的响应格式
        if 'choices' in result and len(result['choices']) > 0:
            # OpenAI格式
            if 'message' in result['choices'][0] and 'content' in result['choices'][0]['message']:
                return result['choices'][0]['message']['content'].strip()
            # 其他格式
            elif 'text' in result['choices'][0]:
                return result['choices'][0]['text'].strip()
        elif 'content' in result:
            # 直接返回content
            return result['content'].strip()
        elif 'response' in result:
            # 某些API返回response字段
            return result['response'].strip()
        
        # 如果都不符合，打印响应结构以便调试
        print(f"API响应结构不符合预期: {result}")
        return None
    except Exception as e:
        print(f"调用API失败: {e}")
        # 尝试打印响应内容以便调试
        try:
            print(f"响应状态码: {response.status_code}")
            print(f"响应内容: {response.text[:500]}")
        except:
            pass
        return None

def format_summary(summary):
    """格式化总结内容，确保符合markdown的> [!NOTE]语法"""
    lines = summary.split('\n')
    formatted_lines = []
    
    for line in lines:
        if line.strip() == '':
            # 空行替换为>
            formatted_lines.append('>')
        else:
            # 非空行保持原样
            formatted_lines.append(line)
    
    # 确保最后有一个空行（用于与---之间留出空隙）
    if formatted_lines and formatted_lines[-1] != '':
        formatted_lines.append('')
    
    return '\n'.join(formatted_lines)

def update_md_file(filepath, summary):
    """更新md文件中的概要部分"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 格式化总结内容
    formatted_summary = format_summary(summary)
    
    # 匹配"> [!NOTE] 概要\n > "模式并替换
    # 使用更宽松的匹配模式，允许空白字符
    pattern = r'(> \[!NOTE\] 概要)\s*\n\s*(>)\s*'
    
    # 使用回调函数避免总结内容中的特殊字符被解释为正则表达式
    def replace_match(match):
        return match.group(1) + '\n' + match.group(2) + ' ' + formatted_summary + '\n'
    
    new_content = re.sub(pattern, replace_match, content)
    
    # 检查是否成功替换
    if new_content == content:
        print(f"警告：未找到匹配的模式，文件未更新: {filepath}")
    else:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"已更新文件: {filepath}")

def get_program_dir():
    """获取程序所在目录（兼容pyinstaller打包）"""
    if getattr(sys, 'frozen', False):
        # pyinstaller打包后的exe模式
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 普通Python脚本模式
        return os.path.dirname(os.path.abspath(__file__))

def main():
    """主函数"""
    # 获取程序所在目录
    script_dir = get_program_dir()
    print(f"程序目录: {script_dir}")
    print("开始处理日记文件...")
    
    # 读取配置（使用程序目录下的config.ini）
    config_path = os.path.join(script_dir, 'config.ini')
    if not os.path.exists(config_path):
        print(f"错误：未找到配置文件 {config_path}")
        return
    
    config = read_config(config_path)
    print("配置读取完成")
    
    # 获取所有md文件（使用程序目录下的md文件）
    md_files = get_md_files(script_dir)
    if not md_files:
        print("未找到符合格式的md文件")
        return
    
    print(f"找到 {len(md_files)} 个md文件")
    
    # 处理每个文件
    for md_file in md_files:
        print(f"\n处理文件: {os.path.basename(md_file)}")
        
        # 读取文件内容
        content = read_md_file(md_file)
        
        # 检查是否已有概要内容（要求>后面有实际文字内容，而不是空白）
        lines = content.split('\n')
        has_summary = False
        for i, line in enumerate(lines):
            if '> [!NOTE] 概要' in line:
                # 找到概要部分，检查下一行
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # 下一行应该以>开头，如果后面有内容则认为已有概要
                    if next_line.startswith('>') and len(next_line) > 1:
                        # 检查>后面是否有实际内容（不是只有空白）
                        content_after_quote = next_line[1:].strip()
                        if content_after_quote:
                            has_summary = True
                            break
        if has_summary:
            print("该文件已有概要内容，跳过")
            continue
        
        # 调用AI获取总结
        summary = call_ai_api(config, content)
        if not summary:
            print("未能获取总结，跳过")
            continue
        
        # 更新文件
        update_md_file(md_file, summary)
    
    print("\n处理完成！")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"程序运行出错: {e}")
    finally:
        print("\n按任意键退出...")
        # 兼容Python和exe环境
        try:
            # Windows命令行
            import msvcrt
            msvcrt.getch()
        except ImportError:
            # 其他平台或IDE
            input()