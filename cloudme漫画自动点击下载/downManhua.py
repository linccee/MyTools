import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, Tuple
import shutil

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


URL = 'https://cloudme.one/refs/28212/1727581'
COUNT = 20

@dataclass
class Config:
	url: str 
	count: int 
	download_dir: Path = Path(r"/Volumes/Zylon/manhua/kjywmm")
	chromedriver_path: Optional[Path] = Path(r"/Users/suzilong/Toolenv/chromedriver-mac-arm64/chromedriver")

	def __post_init__(self):
		# 如果 parse_args 显式传入了 None（覆盖了 dataclass 的默认值），在初始化后恢复为类定义的默认路径，
		# 以优先使用本地 chromedriver 文件，避免自动下载失败的问题。
		if self.chromedriver_path is None:
			self.chromedriver_path = type(self).__dataclass_fields__["chromedriver_path"].default
	headless: bool = False
	per_download_timeout: int = 600  # seconds
	page_load_timeout: int = 60  # seconds
	implicit_wait: int = 0


def _now_str():
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_driver(cfg: Config) -> webdriver.Chrome:
	options = ChromeOptions()
	if cfg.headless:
		# Use the new headless mode for better parity (Chrome >= 109)
		options.add_argument("--headless=new")
	options.add_argument("--disable-gpu")
	options.add_argument("--no-sandbox")
	options.add_argument("--disable-dev-shm-usage")
	options.add_argument("--window-size=1280,900")

	prefs = {
		"download.default_directory": str(cfg.download_dir.resolve()),
		"download.prompt_for_download": False,
		"download.directory_upgrade": True,
		# Allow multiple automatic downloads
		"profile.default_content_setting_values.automatic_downloads": 1,
		# Reduce SafeBrowsing interruptions on some file types
		"safebrowsing.enabled": True,
	}
	options.add_experimental_option("prefs", prefs)

	# 优先使用用户提供的本地 chromedriver
	driver_path = None
	if cfg.chromedriver_path:
		cd_path = Path(cfg.chromedriver_path)
		if not cd_path.exists():
			raise RuntimeError(f"指定的 chromedriver 路径不存在: {cfg.chromedriver_path}")
		driver_path = str(cd_path)
	else:
		# 尝试使用 webdriver-manager 自动为当前浏览器版本获取匹配的 chromedriver。
		try:
			wm_module = __import__("webdriver_manager.chrome", fromlist=["ChromeDriverManager"])
			ChromeDriverManager = getattr(wm_module, "ChromeDriverManager")
			driver_path = ChromeDriverManager().install()
		except ImportError:
			# 回退到系统 PATH 中查找 chromedriver
			path_in_path = shutil.which("chromedriver")
			if path_in_path:
				driver_path = path_in_path
			else:
				raise RuntimeError(
					"缺少 webdriver-manager 且未在 PATH 中找到 chromedriver。请安装 webdriver-manager 或使用 --chromedriver-path 指定本地 chromedriver。"
				)

	service = ChromeService(executable_path=driver_path)
	driver = webdriver.Chrome(service=service, options=options)
	driver.set_page_load_timeout(cfg.page_load_timeout)
	if cfg.implicit_wait:
		driver.implicitly_wait(cfg.implicit_wait)
	return driver


def wait_until_clickable(driver: webdriver.Chrome, locator: Tuple[str, str], timeout: int = 30):
	return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))


def snapshot_existing_files(download_dir: Path) -> Set[Path]:
	return {p for p in download_dir.glob("*") if p.is_file() and not p.name.endswith(".crdownload")}


def any_partial_downloads(download_dir: Path) -> bool:
	return any(p.name.endswith(".crdownload") for p in download_dir.glob("*.crdownload"))


def wait_for_new_file_and_completion(
	download_dir: Path,
	before: Set[Path],
	timeout: int,
	expect_exts: Tuple[str, ...] = (".cbz", ".zip"),
) -> Optional[Path]:
	"""
	Wait for a new file to appear (not present in 'before') and for all .crdownload files to finish.
	If expect_exts provided, prefer returning a file with one of these extensions.
	"""
	deadline = time.time() + timeout
	chosen: Optional[Path] = None
	while time.time() < deadline:
		# Detect new completed files
		current = snapshot_existing_files(download_dir)
		new_files = [p for p in current - before]
		if new_files:
			# Prefer expected extensions
			prioritized = [p for p in new_files if p.suffix.lower() in expect_exts]
			chosen = prioritized[0] if prioritized else new_files[0]

		# Wait for partials to finish
		if not any_partial_downloads(download_dir):
			if chosen and chosen.exists():
				return chosen
			# Even if no chosen yet, if there are no partials and a new file exists, return one
			if new_files:
				return new_files[0]

		time.sleep(1)
	return chosen  # Could be None if nothing appeared


def find_download_button(driver: webdriver.Chrome) -> Optional[webdriver.Chrome]:
	x = "//button[not(@disabled) and contains(normalize-space(.), '下载')]"
	try:
		return wait_until_clickable(driver, (By.XPATH, x), timeout=30)
	except TimeoutException:
		return None


def find_next_button(driver: webdriver.Chrome) -> Optional[webdriver.Chrome]:
	x = "//button[not(@disabled) and contains(normalize-space(.), '下一章')]"
	try:
		return wait_until_clickable(driver, (By.XPATH, x), timeout=30)
	except TimeoutException:
		return None


def get_download_container_signature(driver: webdriver.Chrome) -> Optional[str]:
	"""Return a short signature that likely changes per chapter (e.g., the '已加载: X/Y' text)."""
	try:
		# Anchor to the area containing the 下载 button and the 已加载 text
		container = driver.find_element(By.XPATH, "(//button[contains(normalize-space(.), '下载')]/ancestor::div[contains(@class,'flex')])[1]")
		# Try to find the '已加载' text within the same container
		try:
			loaded = container.find_element(By.XPATH, ".//div[contains(., '已加载')]//span").text.strip()
		except NoSuchElementException:
			loaded = container.text.strip()
		return loaded
	except Exception:
		return None


def wait_for_container_signature_change(driver: webdriver.Chrome, prev_sig: Optional[str], timeout: int = 60) -> bool:
	deadline = time.time() + timeout
	while time.time() < deadline:
		try:
			sig = get_download_container_signature(driver)
		except StaleElementReferenceException:
			sig = None
		if prev_sig is None:
			if sig is not None:
				return True
		else:
			if sig is not None and sig != prev_sig:
				return True
		time.sleep(0.5)
	return False


def run_download_loop(cfg: Config) -> None:
	print(f"[{_now_str()}] 程序启动，配置信息:")
	print(f"  URL: {cfg.url}")
	print(f"  循环次数: {cfg.count}")
	print(f"  下载目录: {cfg.download_dir}")
	print(f"  无头模式: {cfg.headless}")
	print(f"  下载超时: {cfg.per_download_timeout}秒")
	print(f"  页面加载超时: {cfg.page_load_timeout}秒")
	
	try:
		cfg.download_dir.mkdir(parents=True, exist_ok=True)
		print(f"[{_now_str()}] 下载目录已创建/确认存在: {cfg.download_dir}")
	except Exception as e:
		print(f"[{_now_str()}] 错误：无法创建下载目录: {e}", file=sys.stderr)
		return
	
	print(f"[{_now_str()}] 正在启动浏览器...")
	try:
		driver = build_driver(cfg)
		print(f"[{_now_str()}] 浏览器启动成功")
	except Exception as e:
		print(f"[{_now_str()}] 错误：无法启动浏览器: {e}", file=sys.stderr)
		return
	
	try:
		print(f"[{_now_str()}] 打开页面: {cfg.url}")
		driver.get(cfg.url)
		print(f"[{_now_str()}] 页面加载完成")

		# Optional: wait for initial 下载 按钮出现
		print(f"[{_now_str()}] 正在查找'下载'按钮...")
		btn = find_download_button(driver)
		if not btn:
			print(f"[{_now_str()}] 错误：未找到'下载'按钮，请确认页面是否正确加载或需要登录。", file=sys.stderr)
			print(f"[{_now_str()}] 当前页面标题: {driver.title}")
			print(f"[{_now_str()}] 当前页面URL: {driver.current_url}")
			return
		
		print(f"[{_now_str()}] 找到'下载'按钮，开始下载循环")

		for i in range(cfg.count):
			print(f"[{_now_str()}] 开始第 {i + 1}/{cfg.count} 次下载…")

			# Capture signature for this chapter (used to detect next chapter load)
			chapter_sig = get_download_container_signature(driver)

			# Snapshot existing files
			before_files = snapshot_existing_files(cfg.download_dir)

			# Click 下载
			btn = find_download_button(driver)
			if not btn:
				raise RuntimeError("无法找到可点击的'下载'按钮。")
			btn.click()

			# Wait for a new file and for completion (.crdownload cleared)
			downloaded = wait_for_new_file_and_completion(
				cfg.download_dir, before_files, timeout=cfg.per_download_timeout
			)
			if downloaded is None:
				print(f"[{_now_str()}] 警告：未检测到新文件，但将继续下一步。")
			else:
				print(f"[{_now_str()}] 下载完成: {downloaded.name}")

			# Optionally also wait until the '下载'按钮恢复为可点击，避免重复打包窗口未关闭
			try:
				WebDriverWait(driver, 60).until(
					EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.), '下载') and not(@disabled)]"))
				)
			except TimeoutException:
				pass

			# Click 下一章（如果存在）
			next_btn = find_next_button(driver)
			if not next_btn:
				print(f"[{_now_str()}] 未找到'下一章'按钮，可能是最后一章。结束。")
				break
			next_btn.click()

			# 等待新章节内容加载（签名变化）
			if not wait_for_container_signature_change(driver, chapter_sig, timeout=120):
				print(f"[{_now_str()}] 提示：章节内容未在期望时间内发生变化。继续尝试…")

			# 小憩一下，避免过快操作
			time.sleep(1.0)

		print(f"[{_now_str()}] 任务完成。")
	except Exception as e:
		print(f"[{_now_str()}] 运行时错误: {e}", file=sys.stderr)
		import traceback
		traceback.print_exc()
	finally:
		# 保留浏览器窗口以便检查？若需要关闭可改为 driver.quit()
		try:
			print(f"[{_now_str()}] 正在关闭浏览器...")
			driver.quit()
			print(f"[{_now_str()}] 浏览器已关闭")
		except Exception as e:
			print(f"[{_now_str()}] 关闭浏览器时出错: {e}", file=sys.stderr)


def parse_args(argv=None) -> Config:
	parser = argparse.ArgumentParser(
		description="自动化打开漫画页面，批量点击‘下载’并按‘下一章’前进，共执行 N 次。",
		formatter_class=argparse.ArgumentDefaultsHelpFormatter,
	)
	parser.add_argument("--url", dest="url",required=False, default=URL, help="目标页面 manga_URL")
	parser.add_argument("--count", dest="count", type=int, required=False,default=COUNT, help="循环次数 N")
	parser.add_argument(
		"--download-dir",
		dest="download_dir",
		# 默认留空则使用 Config 数据类中的默认下载目录
		default=None,
		help="下载目录（将自动创建）",
	)
	parser.add_argument("--headless", action="store_true", help="使用无头模式运行 Chrome")
	parser.add_argument("--per-download-timeout", type=int, default=600, help="单次下载最大等待秒数")
	parser.add_argument("--page-load-timeout", type=int, default=60, help="页面加载超时秒数")
	parser.add_argument(
		"--chromedriver-path",
		dest="chromedriver_path",
		default=None,
		help="本地 chromedriver 可执行文件的路径（优先）",
	)
	args = parser.parse_args(argv)

	return Config(
		url=args.url,
		count=args.count,
		download_dir=Path(args.download_dir)
		if args.download_dir
		else Config.__dataclass_fields__["download_dir"].default,
	chromedriver_path=Path(args.chromedriver_path) if args.chromedriver_path else None,
		headless=args.headless,
		per_download_timeout=args.per_download_timeout,
		page_load_timeout=args.page_load_timeout,
	)


def main(argv=None):
	print(f"[{_now_str()}] 漫画下载器启动中...")
	try:
		cfg = parse_args(argv)
		run_download_loop(cfg)
	except KeyboardInterrupt:
		print(f"\n[{_now_str()}] 用户中断，程序退出。")
	except Exception as e:
		print(f"[{_now_str()}] 程序异常退出: {e}", file=sys.stderr)
		import traceback
		traceback.print_exc()
	finally:
		print(f"[{_now_str()}] 程序结束。")


if __name__ == "__main__":
	main()
