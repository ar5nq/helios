# Telegram Alerts Setup

One-time setup so signals and news alerts land in your Telegram:

1. Open Telegram, search for **@BotFather**, start a chat.
2. Send `/newbot`, follow the prompts (pick a name and a username ending in `bot`).
3. BotFather replies with a **token** like `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`. Copy it.
4. Send your new bot any message (e.g. "hi") -- it needs at least one message from you to find your chat.
5. In a browser, visit:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   (replace `<YOUR_TOKEN>` with the token from step 3)
6. Look for `"chat":{"id":123456789,...}` in the response -- that number is your **chat id**.
7. Create a `.env` file in the project root (copy `.env.example`) and fill in both values.
8. Install `python-dotenv` (already in requirements.txt) and load it at the top of anything
   that needs these vars, or just export them in your shell before running:
   ```bash
   export TELEGRAM_BOT_TOKEN="123456789:ABCdefGhIJKlmNoPQRstuVWXyz"
   export TELEGRAM_CHAT_ID="123456789"
   ```

**Never commit your real `.env` file or paste your token in chat/screenshots** -- treat it like a password.
`.env` is already in `.gitignore` so it won't accidentally get pushed to GitHub.
