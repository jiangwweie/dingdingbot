#!/usr/bin/env python3
"""Owner-run hidden-input setup. Never run this through a transcript/logging bot."""

from __future__ import annotations

import argparse
import getpass
import json
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trading_kernel.install_manual_host import (
    ManualHostTarget,
    SshManualInstallationBackend,
)
from src.trading_kernel.infrastructure.manual_account_setup import (
    ManualAccountCredentials,
)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", required=True)
    p.add_argument("--machine-id", required=True)
    p.add_argument("--public-ip", required=True)
    args = p.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError(
            "run account setup yourself in an interactive private terminal"
        )
    target = ManualHostTarget(
        ssh_target=args.target, machine_id=args.machine_id, public_ip=args.public_ip
    )
    commit = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=REPO_ROOT, text=True
    ).strip()
    facts = SshManualInstallationBackend(target, commit).inspect()
    if not facts.get("database_prepared") or facts.get("staged_commit") != commit:
        raise ValueError(
            "exact candidate and database foundation must be prepared before entering secrets"
        )
    uid = input("子账户 UID（请从币安子账户详情核对）: ").strip()
    key = getpass.getpass("子账户 API Key（隐藏输入）: ").strip()
    secret = getpass.getpass("子账户 API Secret（隐藏输入）: ").strip()
    username = input("新控制台用户名 [owner]: ").strip() or "owner"
    password = getpass.getpass("新控制台密码（至少12位，隐藏输入）: ")
    confirm = getpass.getpass("再次输入控制台密码: ")
    if password != confirm or len(password) < 12:
        raise ValueError("passwords differ or shorter than 12 characters")
    ManualAccountCredentials(
        expected_uid=uid,
        api_key=key,
        api_secret=secret,
        owner_username=username,
        owner_password=password,
    )
    payload = json.dumps(
        {
            "expected_uid": uid,
            "api_key": key,
            "api_secret": secret,
            "owner_username": username,
            "owner_password": password,
        }
    ).encode()
    launcher = """import json,os,pathlib,subprocess,sys
p=pathlib.Path('/etc/brc/manual-install/staged-release.json'); r=json.loads(p.read_text())
assert pathlib.Path('/etc/machine-id').read_text().strip()==sys.argv[1]
assert pathlib.Path('/etc/brc/product-id').read_text().strip()=='brc-app-manual-v1'
assert r['commit']==sys.argv[2]
assert pathlib.Path('/etc/brc/trading-kernel.write-fenced').is_file()
os.chdir(r['kernel_release'])
os.execv(r['api_release']+'/.venv-owner-console/bin/python',[r['api_release']+'/.venv-owner-console/bin/python','-m','scripts.trading_kernel.manual_account_enrollment','--setup'])
"""
    cmd = (
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        target.ssh_target,
        "--",
        shlex.join(
            ("sudo", "-n", "python3", "-c", launcher, target.machine_id, commit)
        ),
    )
    result = subprocess.run(
        cmd, input=payload, capture_output=True, check=False, timeout=150
    )
    del payload, key, secret, password, confirm
    if result.returncode:
        print("配置未完成。请核对子账户UID、API权限、IP白名单及服务器返回的脱敏错误。")
        try:
            print(
                json.loads(result.stdout).get("message", "readonly verification failed")
            )
        except (ValueError, TypeError):
            pass
        return 1
    reply = json.loads(result.stdout)
    # Enrollment belongs only on the Owner's private terminal, never report files.
    with open("/dev/tty", "w") as tty:
        tty.write(
            "\n仅在你自己的验证器中导入以下TOTP链接，不要发送到聊天或保存终端日志：\n"
        )
        tty.write(reply.pop("totp_enrollment_uri") + "\n")
    print("账户身份和权限已只读核对；密钥已写入新机受保护文件。")
    print(json.dumps(reply, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError):
        print("配置失败；凭据未打印。请核对输入和SSH连接。", file=sys.stderr)
        raise SystemExit(1) from None
