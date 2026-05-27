"""一键启动：新闻服务器 + ngrok 公网隧道"""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
NGROK_BIN = Path("C:/Users/30916/ngrok.exe")
NGROK_URL = "angling-endorse-moody.ngrok-free.dev"


def main():
    print("=" * 50)
    print("  新闻聚合系统启动中...")
    print("=" * 50)

    # 1. Start the news server
    print("\n[1/2] 启动新闻服务器 (localhost:8888)...")
    server = subprocess.Popen(
        [sys.executable, str(ROOT / "server.py")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(3)

    # 2. Start ngrok tunnel
    print("[2/2] 启动 ngrok 公网隧道...")
    ngrok = subprocess.Popen(
        [str(NGROK_BIN), "http", f"--url={NGROK_URL}", "8888"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(3)

    local_url = "http://localhost:8888"
    public_url = f"https://{NGROK_URL}"

    print()
    print("=" * 50)
    print("  系统已启动！")
    print(f"  本地访问: {local_url}")
    print(f"  公网访问: {public_url}")
    print("  按 Ctrl+C 停止")
    print("=" * 50)

    webbrowser.open(local_url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        ngrok.terminate()
        server.terminate()
        print("已停止。")


if __name__ == "__main__":
    main()
