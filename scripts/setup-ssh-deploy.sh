#!/bin/bash
# SSH 免密登录配置脚本
# 用法：./setup-ssh-deploy.sh

set -e

SERVER_HOST="45.76.111.81"
SERVER_USER="root"
SERVER_PASSWORD="G@9fFJb#HG@AgDJ7"  # ⚠️ 首次配置需要，完成后请立即修改！

echo "======================================"
echo "  SSH 免密登录配置脚本"
echo "======================================"

# 检查是否有 sshpass
if ! command -v sshpass &> /dev/null; then
    echo "❌ 未找到 sshpass，正在安装..."
    if command -v brew &> /dev/null; then
        brew install sshpass
    elif command -v apt-get &> /dev/null; then
        sudo apt-get install -y sshpass
    elif command -v yum &> /dev/null; then
        sudo yum install -y sshpass
    else
        echo "请手动安装 sshpass"
        exit 1
    fi
fi

# 生成 SSH 密钥（如果不存在）
if [ ! -f ~/.ssh/id_ed25519 ]; then
    echo "📝 生成 SSH 密钥对..."
    ssh-keygen -t ed25519 -C "dingdingbot_deploy_key" -f ~/.ssh/id_ed25519 -N ""
else
    echo "✅ SSH 密钥已存在：~/.ssh/id_ed25519"
fi

# 显示公钥内容
echo ""
echo "📋 您的 SSH 公钥内容："
echo "======================================"
cat ~/.ssh/id_ed25519.pub
echo "======================================"
echo ""

# 使用 sshpass + ssh-copy-id 自动上传公钥
echo "🔐 正在上传公钥到服务器..."
sshpass -p "${SERVER_PASSWORD}" ssh-copy-id -o StrictHostKeyChecking=no ${SERVER_USER}@${SERVER_HOST}

echo ""
echo "✅ 公钥上传成功！"
echo ""

# 测试免密登录
echo "🧪 测试免密登录..."
if ssh -o StrictHostKeyChecking=no -o BatchMode=yes ${SERVER_USER}@${SERVER_HOST} "echo '登录成功'" > /dev/null 2>&1; then
    echo "✅ 免密登录测试成功！"
else
    echo "❌ 免密登录测试失败，请检查密码是否正确"
    exit 1
fi

echo ""
echo "======================================"
echo "  配置完成！"
echo "======================================"
echo ""
echo "现在可以使用以下命令免密登录："
echo "  ssh root@45.76.111.81"
echo ""
echo "⚠️  安全提醒：请立即修改服务器默认密码！"
echo "  passwd"
echo ""
