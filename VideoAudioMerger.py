import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, StringVar
from PIL import Image, ImageTk
from tkinterdnd2 import TkinterDnD, DND_FILES  # 导入 tkinterdnd2
import threading
import ctypes

class VideoAudioMerger(TkinterDnD.Tk):  # 继承自 TkinterDnD.Tk
    def __init__(self):
        super().__init__()
        self.title("视频音轨合并工具")
        self.geometry("590x550")  # 设置窗口大小

        self.video_path = None
        self.audio_path = None
        self.output_path = "无"  # 默认输出路径为“无”
        self.output_format = StringVar(value="mp4")  # 默认输出格式为mp4

        # 视频选择行
        self.video_frame = tk.Frame(self)
        self.video_frame.pack(pady=10)
        self.video_button = tk.Button(self.video_frame, text="选择视频文件", command=self.select_video)
        self.video_button.pack(side=tk.LEFT)
        self.video_label = tk.Label(self.video_frame, text="未选择视频文件", width=40)
        self.video_label.pack(side=tk.LEFT, padx=5)
        # 删除视频按钮
        self.delete_button = tk.Button(self.video_frame, text="删除视频", command=self.clear_video)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        # 添加拖拽功能
        self.video_drag_frame = tk.Frame(self)
        self.video_drag_frame.pack(pady=10)
        self.video_drag_label = tk.Label(self.video_drag_frame, text="将视频文件拖拽到此处", relief="groove", width=50, height=5)
        self.video_drag_label.pack()
        self.video_drag_label.drop_target_register(DND_FILES)
        self.video_drag_label.dnd_bind('<<Drop>>', self.drop_video)

        # 检查 ffmpeg 是否安装
        if not self.is_ffmpeg_installed():
            messagebox.showerror("错误", "没有检测到 ffmpeg，请先安装或检查环境变量。", command=self.exit_program)

        # 保存缩略图引用
        self.video_thumbnail = None  # 保证缩略图对象不会被GC回收

        # 音频选择行
        self.audio_frame = tk.Frame(self)
        self.audio_frame.pack(pady=10)
        self.audio_button = tk.Button(self.audio_frame, text="选择音频文件", command=self.select_audio)
        self.audio_button.pack(side=tk.LEFT)
        self.audio_label = tk.Label(self.audio_frame, text="未选择音频文件", width=40)
        self.audio_label.pack(side=tk.LEFT, padx=5)

        # 添加音频拖拽功能
        self.audio_drag_frame = tk.Frame(self)
        self.audio_drag_frame.pack(pady=10)
        self.audio_drag_label = tk.Label(self.audio_drag_frame, text="将音频文件拖拽到此处", relief="groove", width=50, height=5)
        self.audio_drag_label.pack()
        self.audio_drag_label.drop_target_register(DND_FILES)
        self.audio_drag_label.dnd_bind('<<Drop>>', self.drop_audio)

        # 删除音频按钮放置在音频路径右边
        self.delete_audio_button = tk.Button(self.audio_frame, text="删除音频", command=self.clear_audio)
        self.delete_audio_button.pack(side=tk.LEFT, padx=5)

        # 输出文件名和格式行
        self.output_frame = tk.Frame(self)
        self.output_frame.pack(pady=10)
        self.output_label = tk.Label(self.output_frame, text="输出文件名 :")
        self.output_label.pack(side=tk.LEFT)
        self.output_entry = tk.Entry(self.output_frame)
        self.output_entry.pack(side=tk.LEFT, padx=5)
        self.output_entry.insert(0, "output")

        # 输出格式下拉列表
        self.format_dropdown = tk.OptionMenu(self.output_frame, self.output_format, "mp4", "mkv", "avi", "mov", "flv")
        self.format_dropdown.pack(side=tk.LEFT, padx=5)

        # 输出路径选择行
        self.output_path_frame = tk.Frame(self)
        self.output_path_frame.pack(pady=10)
        self.output_button = tk.Button(self.output_path_frame, text="选择输出文件夹", command=self.select_output)
        self.output_button.pack(side=tk.LEFT)
        self.output_label_path = tk.Label(self.output_path_frame, text=self.output_path)
        self.output_label_path.pack(side=tk.LEFT, padx=5)

        # 合并按钮
        self.merge_button = tk.Button(self, text="合并视频和音频", command=self.merge_video_audio)
        self.merge_button.pack(pady=20)

    def is_ffmpeg_installed(self):
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except subprocess.CalledProcessError:
            return False
        except FileNotFoundError:
            return False

    def exit_program(self):
        self.destroy()

    def get_resource_path(relative_path):
        # 打包后的路径
        if getattr(sys, 'frozen', False):
            # 如果是 frozen exe 程序
            base_path = sys._MEIPASS
        else:
            # 如果是开发模式下
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)
    def get_thumbnail(self, file_path):
        """通过读取视频文件的首帧生成缩略图"""
        ffmpeg_path = self.find_ffmpeg()
        if not ffmpeg_path:
            return None

        # 删除现有的临时缩略图文件
        temp_thumbnail_path = "temp_thumbnail.png"
        if os.path.exists(temp_thumbnail_path):
            os.remove(temp_thumbnail_path)

        # 使用 ffmpeg 生成缩略图并保存为临时文件
        cmd = [
            ffmpeg_path,
            '-i', file_path,
            '-ss', '00:00:3',  # 从3秒处提取缩略图
            '-vframes', '1',     # 提取一帧图像
            '-f', 'image2',
            temp_thumbnail_path
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # 使用 PIL 打开临时生成的缩略图
            img = Image.open(temp_thumbnail_path)
            # 获取原图大小并调整为原大小的 40%
            original_width, original_height = img.size
            new_width = int(original_width * 0.4)
            new_height = int(original_height * 0.4)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)  # 调整为 40% 的大小
            return img
        except Exception as e:
            print(f"生成缩略图时出错: {e}")
            return None


    def drop_video(self, event):
        self.video_path = event.data.strip('{').strip('}')
        if self.video_path:
            self.video_label.config(text=self.video_path)
            self.output_path = os.path.dirname(self.video_path)
            self.output_label_path.config(text=self.output_path)
            thumbnail = self.get_thumbnail(self.video_path)
            threading.Thread(target=self.async_get_thumbnail, args=(self.video_path,)).start()
            if thumbnail:
                self.video_thumbnail = ImageTk.PhotoImage(thumbnail)  # 保持对图像的引用
                self.video_drag_label.config(image=self.video_thumbnail, text="")  # 更新 Label 显示图像

                # 动态调整 Label 大小
                width, height = thumbnail.size  # 获取缩略图的宽度和高度
                self.video_drag_label.config(width=width, height=height)  # 更新 Label 的宽高

                # 调整窗口大小以容纳缩略图，并加一些边距
                self.geometry(f"{width + 220}x{height + 550}")  # 设置窗口大小（额外加些边距）

                # 清理临时文件
                os.remove(self.get_resource_path('temp_thumbnail.png'))
            else:
                self.video_drag_label.config(text="无法生成缩略图")
        else:
            self.output_path = "无"
            self.output_label_path.config(text=self.output_path)
            self.video_drag_label.config(image="", text="将视频文件拖拽到此处")

            # 如果没有视频，恢复到初始状态
            self.video_drag_label.config(width=50, height=5)  # 重置拖拽框的默认大小
            self.geometry("590x550")  # 恢复到窗口的原始大小




    def async_get_thumbnail(self, file_path):
        """异步获取缩略图"""
        thumbnail = self.get_thumbnail(file_path)
        if thumbnail:
            # 更新界面需要在主线程中执行
            self.after(0, self.update_thumbnail, thumbnail)
        else:
            self.after(0, self.update_thumbnail, None)

    def update_thumbnail(self, thumbnail):
        """更新界面元素"""
        if thumbnail:
            self.video_thumbnail = ImageTk.PhotoImage(thumbnail)  # 保持对图像的引用
            self.video_drag_label.config(image=self.video_thumbnail, text="")  # 更新 Label 显示图像

            # 动态调整 Label 大小
            width, height = thumbnail.size  # 获取缩略图的宽度和高度
            self.video_drag_label.config(width=width, height=height)  # 更新 Label 的宽高

            # 调整窗口大小为图像大小（加上一些额外的边距）
            self.geometry(f"{width + 220}x{height + 550}")  # 设置窗口大小（额外加些边距）
            self.update()  # 强制更新界面
        else:
            self.video_drag_label.config(text="无法生成缩略图")

    def clear_video(self):
        """清除视频路径和显示"""
        self.video_path = None
        self.video_label.config(text="未选择视频文件")  # 更新标签文本
        self.output_path = "无"  # 输出路径重置
        self.output_label_path.config(text=self.output_path)
        self.video_drag_label.config(image="", text="将视频文件拖拽到此处")  # 重置拖拽区域的显示
        # 重置拖拽框的大小
        self.video_drag_label.config(width=50, height=5)
        # 恢复窗口的原始大小
        self.geometry("590x550")  # 这里的 590x550 是窗口的初始大小，根据需要修改

    # 使用PIL库从图标句柄获取图像
    def extract_icon(self, file_path):
        try:
            SHGFI_ICON = 0x100  # 获取图标
            SHGFI_LARGEICON = 0x0  # 大图标
            SHGFI_SMALLICON = 0x1  # 小图标
            MAX_PATH = 260

            class SHFILEINFO(ctypes.Structure):
                _fields_ = [
                    ("hIcon", ctypes.c_void_p),
                    ("iIcon", ctypes.c_int),
                    ("dwAttributes", ctypes.c_uint),
                    ("szDisplayName", ctypes.c_wchar * MAX_PATH),
                    ("szTypeName", ctypes.c_wchar * 80)
                ]

            # 获取文件图标
            shinfo = SHFILEINFO()
            result = ctypes.windll.shell32.SHGetFileInfoW(
                file_path,
                0,
                ctypes.byref(shinfo),
                ctypes.sizeof(SHFILEINFO),
                SHGFI_ICON | SHGFI_LARGEICON
            )

            print(f"SHGetFileInfo result: {result}")  # 输出返回值，0 表示失败

            icon_handle = shinfo.hIcon
            if icon_handle:
                icon = Image.open(icon_handle)
                print("图标提取成功")
                return icon
            else:
                print("没有提取到图标")
                return None
        except Exception as e:
            print(f"提取图标时发生错误: {e}")
            return None


    def drop_audio(self, event):
        self.audio_path = event.data.strip('{').strip('}')
        if self.audio_path:
            self.audio_label.config(text=self.audio_path)
            self.audio_drag_label.config(text="")  # 清除拖拽区域的文字
            try:
                # 尝试从音频文件提取图标
                audio_icon = self.extract_icon(self.audio_path)
                if audio_icon:
                    audio_icon = audio_icon.resize((50, 50), Image.Resampling.LANCZOS)
                else:
                    # 如果无法提取图标，使用默认的音频图标
                    audio_icon = Image.open(self.get_resource_path("default_audio_icon.png"))  # 假设你有一个默认图标
                    audio_icon = audio_icon.resize((50, 50), Image.Resampling.LANCZOS)

                self.audio_icon = ImageTk.PhotoImage(audio_icon)
                self.audio_drag_label.config(image=self.audio_icon)
                self.audio_drag_label.config(width=50, height=50)  # 更新拖拽框大小
            except Exception as e:
                print(f"加载音频图标时出错: {e}")




    def clear_audio(self):
        """清除音频路径和显示"""
        self.audio_path = None
        self.audio_label.config(text="未选择音频文件")  # 更新标签文本
        self.audio_drag_label.config(image="", text="将音频文件拖拽到此处")  # 重置拖拽区域的显示
        self.audio_drag_label.config(width=50, height=5)  # 恢复拖拽框的默认大小

    def select_video(self):
        self.video_path = filedialog.askopenfilename(title="选择视频文件", filetypes=[("视频文件", "*.mp4;*.mkv;*.mov;*.avi")])
        if self.video_path:
            self.video_label.config(text=self.video_path)
            self.output_path = os.path.dirname(self.video_path)
            self.output_label_path.config(text=self.output_path)
        else:
            self.output_path = "无"
            self.output_label_path.config(text=self.output_path)

    def select_audio(self):
        self.audio_path = filedialog.askopenfilename(title="选择音频文件", filetypes=[("音频文件", "*.mp3;*.wav;*.m4a")])
        if self.audio_path:
            self.audio_label.config(text=self.audio_path)

    def select_output(self):
        selected_path = filedialog.askdirectory(title="选择输出文件夹")
        if selected_path:
            self.output_path = selected_path
            self.output_label_path.config(text=self.output_path)

    def merge_video_audio(self):
        if not self.video_path or not self.audio_path:
            messagebox.showerror("错误", "请先选择视频和音频文件。")
            return

        output_filename = self.output_entry.get() or "output"
        output_file_format = self.output_format.get()
        output_file = os.path.join(self.output_path, f"{output_filename}.{output_file_format}")

        ffmpeg_path = self.find_ffmpeg()
        if not ffmpeg_path:
            messagebox.showerror("错误", "未找到 FFmpeg，请确保已安装 FFmpeg。")
            return

        command = [ffmpeg_path, '-i', self.video_path, '-i', self.audio_path, '-codec', 'copy', output_file]

        try:
            subprocess.run(command, check=True)
            messagebox.showinfo("完成", f"视频和音频已合并，输出文件: {output_file}")
        except subprocess.CalledProcessError as e:
            messagebox.showerror("错误", f"合并失败: {e}")

    def find_ffmpeg(self):
        ffmpeg_paths = ["ffmpeg", "ffmpeg.exe"]
        for path in ffmpeg_paths:
            if subprocess.run(['where', path], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0:
                return path
        return None

if __name__ == "__main__":
    app = VideoAudioMerger()
    app.mainloop()
