from client.bot_client import BotClient

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("token", type=str)
parser.add_argument("reset_user_time", type=int)
args = parser.parse_args()

bot = BotClient(bot_token=args.token, reset_time=args.reset_user_time)
bot.start()
