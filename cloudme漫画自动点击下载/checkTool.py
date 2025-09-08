import os
import re
import glob

START_NUM = 122
END_NUM = 400
DIR = 'G:\迅雷下载\mah'
FILE_FORMAT = 'cbz'

def check_files():
    # 检查目录是否存在
    if not os.path.exists(DIR):
        print(f"目录不存在: {DIR}")
        return
    
    # 获取指定格式的所有文件
    pattern = os.path.join(DIR, f"*.{FILE_FORMAT}")
    files = glob.glob(pattern)
    
    if not files:
        print(f"在目录 {DIR} 中未找到任何 .{FILE_FORMAT} 格式的文件")
        return
    
    # 提取文件名中"第"和"话"之间的数字
    found_numbers = set()
    pattern = r'第(\d+)话'
    
    for file_path in files:
        filename = os.path.basename(file_path)
        match = re.search(pattern, filename)
        if match:
            number = int(match.group(1))
            found_numbers.add(number)
    
    # 生成期望的数字范围
    expected_numbers = set(range(START_NUM, END_NUM + 1))
    
    # 检查缺失的数字
    missing_numbers = expected_numbers - found_numbers
    
    if not missing_numbers:
        print("无缺失文件")
    else:
        missing_list = sorted(list(missing_numbers))
        print(f"缺失的文件编号: {missing_list}")
        print(f"共缺失 {len(missing_list)} 个文件")

if __name__ == "__main__":
    check_files()
