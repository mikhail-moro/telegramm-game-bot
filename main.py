import argparse

parser = argparse.ArgumentParser()
parser.add_argument("token", type=str)
parser.add_argument("reset_user_time", type=int)
parser.add_argument("database_name", type=str)
parser.add_argument("database_user", type=str)
parser.add_argument("database_password", type=str)
args = parser.parse_args()

db_conn_kwargs = {
    "host": "localhost",
    "user": args.database_user,
    "password": args.database_password,
    "database": args.database_name
}


from client.bot_client import BotClient

bot = BotClient(
    bot_token=args.token,
    database_conn_kwargs=db_conn_kwargs,
    reset_time=args.reset_user_time
)

bot.start()
