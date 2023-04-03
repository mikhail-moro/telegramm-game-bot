from client.bot_client import BotClient

"""
Будет использоваться в дальнейшем для запуска из файла run_bot.sh

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("token", type=str)
args = parser.parse_args()

print(args)
"""

bot = BotClient(bot_token="6028879461:AAEge0mqpgq-zzMfyKj7NEao8LP0gD9XMU4")
bot.start()
