# SGO Nexa - Luxury Digital Menu & Telegram Bot

This project is a Telegram Bot integrated with a Web App for a digital menu ordering system.

## Features
- **Telegram Bot**: Handles start commands and order notifications.
- **Web App**: Digital menu with categories, cart, and "payment" simulation.
- **Backend**: Python (Aiogram + Aiohttp) serving the web app and running the bot.
- **Database**: SQLite for order tracking.

## Installation on Ubuntu

1.  **Update System**:
    ```bash
    sudo apt update && sudo apt upgrade -y
    sudo apt install python3-pip python3-venv git -y
    ```

2.  **Clone/Copy Project**:
    Copy your project files to `/opt/sgo-nexa` (or any directory you prefer).
    ```bash
    sudo mkdir -p /opt/sgo-nexa
    # (Upload files via SFTP or git clone)
    cd /opt/sgo-nexa
    ```

3.  **Setup Virtual Environment**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

4.  **Configuration**:
    Create a `.env` file from the example (or just edit the provided one).
    ```bash
    cp .env .env.local
    nano .env
    ```
    - Set `API_TOKEN` to your Telegram Bot Token.
    - Set `ADMIN_ID` to your Telegram User ID.
    - Set `BASE_URL` to your domain (HTTPS is required for Telegram Web Apps).

5.  **Run Manually (Test)**:
    ```bash
    python main.py
    ```

6.  **Setup Systemd Service (Auto-start)**:
    Copy the service file:
    ```bash
    sudo cp sgo-nexa.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable sgo-nexa
    sudo systemctl start sgo-nexa
    sudo systemctl status sgo-nexa
    ```

## HTTPS Requirement
Telegram Web Apps **require HTTPS**. You have two options:
1.  **Use a Reverse Proxy (Nginx/Apache)** with Let's Encrypt (Recommended).
    - Run the bot on `127.0.0.1:8000`.
    - Configure Nginx to proxy `https://yourdomain.com` to `http://127.0.0.1:8000`.
2.  **Use ngrok (For Testing)**:
    ```bash
    ngrok http 8000
    ```
    Update `BASE_URL` in `.env` with the ngrok HTTPS URL.
