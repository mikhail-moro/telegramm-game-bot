import argparse
import datetime

from keras.models import load_model

parser = argparse.ArgumentParser()
parser.add_argument("token", type=str)
parser.add_argument("reset_user_time", type=int)
parser.add_argument("use_game_ai", type=int)
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

if args.use_game_ai == 1:
    date = datetime.datetime.today()
    print(f"{str(date)}: Загрузка модели")

    model = load_model("./neural_network/tic-tac-toe_model.h5")
else:
    model = None

from client.bot_client import BotClient

bot = BotClient(
    bot_token=args.token,
    database_conn_kwargs=db_conn_kwargs,
    reset_time=args.reset_user_time,
    model=model
)

bot.start()
