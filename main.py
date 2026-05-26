import os
import re
import sys
import configparser
import requests
from datetime import datetime


def read_config(config_path):
    """读取配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')

    return {
        'url': config.get('ai', 'url'),
        'api_key': config.get('ai', 'api_key'),
        'model_name': config.get('ai', 'model_name'),
        'temperature': float(config.get('ai', 'temperature')),
        'prompt': config.get('prompt', 'prompt'),
        'output_site': config.get('output', 'output_site', fallback='> [!NOTE] 概要'),
        'count': config.getint('base', 'count', fallback=1),
        'log': config.getboolean('log', 'log', fallback=False)
    }


def get_md_files(directory='.'):
    """获取目录下所有符合日期格式的md文件，并按日期排序"""
    md_files = []
    for filename in os.listdir(directory):
        if filename.endswith('.md') and re.match(r'^\d{4}-\d{2}-\d{2}\.md$', filename):
            md_files.append(os.path.join(directory, filename))
    # 按日期名称排序
    md_files.sort()
    return md_files


def read_md_file(filepath):
    """读取md文件内容"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def call_ai_api(config, content, files_sent=None):
    """调用AI API获取总结，返回结果和日志信息"""
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

    log_info = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'files_sent': files_sent if files_sent else [],
        'prompt': system_prompt,
        'raw_response': None,
        'error': None
    }

    try:
        response = requests.post(config['url'], headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        log_info['raw_response'] = result

        # 尝试多种可能的响应格式
        if 'choices' in result and len(result['choices']) > 0:
            # OpenAI格式
            if 'message' in result['choices'][0] and 'content' in result['choices'][0]['message']:
                return result['choices'][0]['message']['content'].strip(), log_info
            # 其他格式
            if 'text' in result['choices'][0]:
                return result['choices'][0]['text'].strip(), log_info
        if 'content' in result:
            # 直接返回content
            return result['content'].strip(), log_info
        if 'response' in result:
            # 某些API返回response字段
            return result['response'].strip(), log_info

        # 如果都不符合，打印响应结构以便调试
        error_msg = f"API响应结构不符合预期: {result}"
        print(error_msg)
        log_info['error'] = error_msg
        return None, log_info
    except Exception as e:
        error_msg = f"调用API失败: {e}"
        print(error_msg)
        log_info['error'] = error_msg
        # 尝试打印响应内容以便调试
        try:
            print(f"响应状态码: {response.status_code}")
            print(f"响应内容: {response.text[:500]}")
        except Exception:
            pass
        return None, log_info


def format_summary(summary):
    """格式化总结内容，确保符合markdown的> [!NOTE]语法"""
    lines = summary.split('\n')
    formatted_lines = []

    for line in lines:
        if line.strip() == '':
            # 空行替换为>
            formatted_lines.append('>')
        else:
            # 如果行已经以>开头，就不再添加，避免出现>>
            stripped_line = line.lstrip()
            if stripped_line.startswith('>'):
                formatted_lines.append(line)
            else:
                # 每行前面都加>，适配不同的md文档渲染软件
                formatted_lines.append('> ' + line)

    # 确保最后有一个空行（用于与---之间留出空隙）
    if formatted_lines and formatted_lines[-1] != '':
        formatted_lines.append('')

    return '\n'.join(formatted_lines)


def update_md_file(filepath, summary, output_site):
    """更新md文件中的概要部分"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 格式化总结内容
    formatted_summary = format_summary(summary)

    # 使用配置中的output_site构建动态正则表达式
    # 需要转义特殊字符
    escaped_output_site = re.escape(output_site)
    pattern = rf'({escaped_output_site})\s*\n\s*>\s*'
    
    # 使用回调函数避免总结内容中的特殊字符被解释为正则表达式
    def replace_match(match):
        return match.group(1) + '\n' + formatted_summary + '\n'

    new_content = re.sub(pattern, replace_match, content)

    # 检查是否成功替换
    if new_content == content:
        print(f"警告：未找到匹配的模式 '{output_site}'，文件未更新: {filepath}")
    else:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"已更新文件: {filepath}")


def get_program_dir():
    """获取程序所在目录（兼容pyinstaller打包）"""
    if getattr(sys, 'frozen', False):
        # pyinstaller打包后的exe模式
        return os.path.dirname(os.path.abspath(sys.executable))
    # 普通Python脚本模式
    return os.path.dirname(os.path.abspath(__file__))


def write_log(log_entries, script_dir, total_files, processed_files, skipped_files, failed_files):
    """写入日志文件，每次运行只保留一个日志文件"""
    # 删除旧的日志文件
    for filename in os.listdir(script_dir):
        if filename.startswith('log_') and filename.endswith('.md'):
            try:
                os.remove(os.path.join(script_dir, filename))
            except:
                pass
    
    # 创建新日志文件
    log_filename = f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    log_path = os.path.join(script_dir, log_filename)

    with open(log_path, 'w', encoding='utf-8') as f:
        f.write("# 日记总结程序日志\n\n")
        f.write(f"## 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## 统计汇总\n\n")
        f.write(f"- 总文件数: {total_files}\n")
        f.write(f"- 已处理文件数: {processed_files}\n")
        f.write(f"- 跳过文件数: {skipped_files}\n")
        f.write(f"- 失败文件数: {failed_files}\n\n")

        if log_entries:
            f.write("## API调用记录\n\n")
            for i, entry in enumerate(log_entries, 1):
                f.write(f"### 调用 #{i}\n\n")
                f.write(f"**时间**: {entry['timestamp']}\n\n")
                f.write("**发送文件**:\n")
                for file in entry['files_sent']:
                    f.write(f"  - `{os.path.basename(file)}`\n")
                f.write(f"\n**提示词**:\n\n{entry['prompt']}\n\n")
                if entry['error']:
                    f.write(f"**错误信息**: {entry['error']}\n\n")
                else:
                    f.write(f"**原始响应**:\n\n```json\n{entry['raw_response']}\n```\n\n")

    print(f"日志已保存: {log_path}")


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

    print(f"找到 {len(md_files)} 个md文件，每次发送 {config['count']} 篇")

    # 日志记录
    log_entries = []
    processed_count = 0
    skipped_count = 0
    failed_count = 0

    # 处理每个文件
    for i, md_file in enumerate(md_files):
        print(f"\n处理文件: {os.path.basename(md_file)}")

        # 读取文件内容
        content = read_md_file(md_file)

        # 检查是否已有概要内容（要求>后面有实际文字内容，而不是空白）
        lines = content.split('\n')
        has_summary = False
        output_site = config['output_site']
        for j, line in enumerate(lines):
            if output_site in line:
                # 找到概要部分，检查下一行
                if j + 1 < len(lines):
                    next_line = lines[j + 1].strip()
                    # 下一行应该以>开头，如果后面有内容则认为已有概要
                    if next_line.startswith('>') and len(next_line) > 1:
                        # 检查>后面是否有实际内容（不是只有空白）
                        content_after_quote = next_line[1:].strip()
                        if content_after_quote:
                            has_summary = True
                            break
        if has_summary:
            print("该文件已有概要内容，跳过")
            skipped_count += 1
            continue

        # 获取需要发送的文件（当前文件及其前count-1个文件）
        start_idx = max(0, i - config['count'] + 1)
        files_to_send = md_files[start_idx:i + 1]

        print(f"发送文件: {[os.path.basename(f) for f in files_to_send]}")

        # 合并多个文件的内容
        combined_content = "\n\n---\n\n".join([read_md_file(f) for f in files_to_send])

        # 调用AI获取总结
        summary, log_info = call_ai_api(config, combined_content, files_to_send)

        # 记录日志
        if config['log']:
            log_entries.append(log_info)

        if not summary:
            print("未能获取总结，跳过")
            failed_count += 1
            continue

        # 更新文件
        update_md_file(md_file, summary, config['output_site'])
        processed_count += 1

    # 写入日志
    if config['log']:
        write_log(log_entries, script_dir, len(md_files), processed_count, skipped_count, failed_count)

    print("\n处理完成！")
    print(f"总文件: {len(md_files)} | 已处理: {processed_count} | 跳过: {skipped_count} | 失败: {failed_count}")


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