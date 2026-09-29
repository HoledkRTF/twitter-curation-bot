#!/bin/bash
# Oracle Cloud VM Setup Script for Twitter Curation Bot
# Run this ONCE after SSH-ing into your new VM

set -e

echo "=== Installing Python and pip ==="
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

echo "=== Creating bot directory ==="
mkdir -p ~/twitter-bot
cd ~/twitter-bot

echo "=== Creating virtual environment ==="
python3 -m venv venv
source venv/bin/activate

echo "=== Installing dependencies ==="
pip install python-telegram-bot==21.11.1 apify-client httpx

echo "=== Writing environment config ==="
cat > .env << 'ENVEOF'
TELEGRAM_BOT_TOKEN=8790529388:AAGGbCA_zGHcpXeCqvl9jisSk17UpqwBfzU
TELEGRAM_CHANNEL_ID=-1003942778636
TWITTER_LIST_URL=https://x.com/i/lists/2078086710118715619
APIFY_API_TOKEN=apify_api_zkccbeiDQQ0gKBLfLgaP62xYQq6tAI09zTLg
ENVEOF

echo "=== Creating systemd service ==="
sudo tee /etc/systemd/system/twitter-bot.service > /dev/null << 'EOF'
[Unit]
Description=Twitter Curation Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/twitter-bot
EnvironmentFile=/home/$USER/twitter-bot/.env
ExecStart=/home/$USER/twitter-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Fix the $USER in the service file
sudo sed -i "s|\$USER|$USER|g" /etc/systemd/system/twitter-bot.service

echo ""
echo "=== SETUP COMPLETE ==="
echo ""
echo "Now upload bot.py to ~/twitter-bot/ and run:"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable twitter-bot"
echo "  sudo systemctl start twitter-bot"
echo ""
echo "To check logs:  sudo journalctl -u twitter-bot -f"
echo "To restart:     sudo systemctl restart twitter-bot"
