import json
import os, sys, stat, paramiko

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".credentials.json")
REMOTE = "/opt/clockwise-ledger"
LOCAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {"node_modules", ".venv", ".localdata", ".shots", "__pycache__", "data", ".git", "tests", "test"}
SKIP_FILES = {"shot.py", "shot2.py", "shot3.py", "shot4.py", "shot5.py", "tools_test.py", ".credentials.json"}

def _default_keyfile():
    """无密码时用的 SSH 钥匙：显式环境变量优先，其次是云电脑上的默认钥匙。"""
    candidates = [os.getenv("LEDGER_DEPLOY_KEY", "")]
    candidates += [os.path.expanduser("~/.ssh/id_ed25519"),
                   "/home/hatch/.ssh/id_ed25519"]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def deployment_credentials():
    local_config = {}
    if os.path.isfile(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, encoding="utf-8") as config_file:
            local_config = json.load(config_file)
    host = os.getenv("LEDGER_DEPLOY_HOST") or local_config.get("host", "")
    user = os.getenv("LEDGER_DEPLOY_USER") or local_config.get("user", "root")
    password = os.getenv("LEDGER_DEPLOY_PASSWORD") or local_config.get("password", "")
    # 密码优先（老用法不变）；没密码时走已配好的 SSH 钥匙，不再要求每次发密码。
    keyfile = "" if password else _default_keyfile()
    if not host or (not password and not keyfile):
        raise ValueError("请配置 LEDGER_DEPLOY_HOST 和 LEDGER_DEPLOY_PASSWORD，或 deploy/.credentials.json，"
                         "或先把 SSH 公钥加到服务器 authorized_keys 后用钥匙登录")
    return host, user, password, keyfile

def walk(base):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if (name in SKIP_FILES or name.endswith((".pyc", ".tsbuildinfo", ".db", ".sqlite", ".sqlite3"))
                    or name == ".env" or name.startswith(".env.")
                    or name.startswith("test_") or name.endswith(("_test.py", "Test.java", "Tests.java"))):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base).replace("\\", "/")
            yield full, rel

def main():
    include_dist = "--with-dist" in sys.argv
    host, user, password, keyfile = deployment_credentials()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        client.connect(host, 22, user, password, timeout=20)
    else:
        client.connect(host, 22, user, key_filename=keyfile, timeout=20)
    sftp = client.open_sftp()

    def ensure_dir(path):
        parts = path.strip("/").split("/")
        current = ""
        for part in parts:
            current += "/" + part
            try:
                sftp.stat(current)
            except IOError:
                sftp.mkdir(current)

    ensure_dir(REMOTE)
    count = 0
    for full, rel in walk(LOCAL):
        if (rel.startswith("frontend/dist/") or rel.startswith("frontend/dist-root/")) and not include_dist:
            continue
        target = f"{REMOTE}/{rel}"
        ensure_dir(os.path.dirname(target))
        sftp.put(full, target)
        count += 1
    print(f"uploaded {count} files -> {REMOTE}")
    sftp.close(); client.close()

if __name__ == "__main__":
    main()
