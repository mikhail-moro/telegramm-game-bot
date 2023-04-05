import time
import datetime
import telebot

from database.database_util import *
from enum import IntEnum, StrEnum
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from game.game import Game, TurnResult, GameResultCode, TurnResultCode


def log(message: str):
    date = datetime.datetime.today()
    print(f"{str(date)}: {message}")


class _Status(IntEnum):
    IS_NOW_CHAT = 0
    IS_NOW_AWAITING_TOKEN = 1
    IS_NOW_GAME = 2


# В данном случае используется StrEnum так как параметр callback_data класса InlineKeyboardMarkup требует
# строчный тип данных входного значения
class _CallData(StrEnum):
    START = "start"
    JOIN = "join"
    TURN = "turn"


class BotClient:
    def __init__(self, bot_token):
        """
        :param bot_token: уникальный токен Telegram-бота
        """

        self._chats_statuses: {int, _Status} = {}
        """
        _chats_statuses: {player_id, status}
        
        Словарь содержащий в себе статусы всех пользователей

        player_id:
            id игрока
        status:
            _Status.IS_NOW_CHAT - еще не идёт игра или поиск сессии \n
            _Status.IS_NOW_AWAITING_TOKEN - ожидается ввод токена для присоеденения к существующей сессии \n
            _Status.IS_NOW_GAME - в данный момент идёт игра
        """
        self._games: [Game] = []
        """ 
        Список всех игр идущих на данный момент
        """
        self.bot = telebot.TeleBot(bot_token, parse_mode=None)
        """
        Текущий экземпляр класса TeleBot содержащий API для управления Telegram-ботом
        """

        # Обрабатывает сообщение если отправивший его пользователь не начал поиск сессии или игру и просто общается с
        # ботом или если это новый пользователь
        @self.bot.message_handler(
            func=lambda message:
                (message.from_user.id not in self._chats_statuses.keys())
                or
                (self._chats_statuses[message.from_user.id] == _Status.IS_NOW_CHAT)
        )
        def chat_message_handler(message: Message):
            player_id = message.from_user.id

            if player_id not in self._chats_statuses.keys():
                self._chats_statuses[player_id] = _Status.IS_NOW_CHAT
                log(f"Новый пользователь {player_id}")

            start_button = InlineKeyboardButton("СТАРТ", callback_data=_CallData.START)
            join_button = InlineKeyboardButton("ПРИСОЕДИНИТЬСЯ", callback_data=_CallData.JOIN)

            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(start_button, join_button)

            self.bot.reply_to(message, text="Нажмите СТАРТ чтобы начать новую игру, или ПРИСОЕДИНИТЬСЯ чтобы "
                                            "присоединиться к существующей", reply_markup=markup)

        # Обрабатывает сообщение если отправивший его пользователь должен ввести токен подключения к существующей сессии
        @self.bot.message_handler(
            func=lambda message: self._chats_statuses[message.from_user.id] == _Status.IS_NOW_AWAITING_TOKEN
        )
        def token_message_handler(message):
            player_id = message.from_user.id
            token = message.text

            if message.text != 'нет':
                game = self.__find_game_by_session_token(token)

                if game is not None:
                    is_join_success = self.__join_to_game(game, player_id)

                    if is_join_success:
                        start_matrix = game.start_game()

                        markup = self.__matrix_to_markup(start_matrix)
                        message_matrix = self.__matrix_to_emojis(start_matrix)

                        turn_player_id = game.turn_now_player.id
                        wait_player_id = game.awaiting_player.id

                        self.bot.send_message(turn_player_id, "Сессия найдена, вы играете за \"X\".\nВаш ход:")
                        self.bot.send_message(turn_player_id, message_matrix, reply_markup=markup)

                        self.bot.send_message(wait_player_id, "Сессия найдена, вы играете за \"О\".\nОжидайте ход "
                                                              "другого игрока...")
                        self.bot.send_message(wait_player_id, message_matrix)

                        self._chats_statuses[turn_player_id] = _Status.IS_NOW_GAME
                        self._chats_statuses[wait_player_id] = _Status.IS_NOW_GAME

                        log(f"Сессия {token}. Игроки - 2")
                else:
                    self.bot.reply_to(message, "Не найдена сессия")
                    self._chats_statuses[player_id] = _Status.IS_NOW_CHAT
            else:
                self._chats_statuses[player_id] = _Status.IS_NOW_CHAT

        # В следующих обработчиках проверяется лишь первый элемент callback_data так как он содержит информацию об
        # нажатой кнопке, остальные элементы будут содержать координаты хода игрока

        # Обрабатывает нажатие на кнопку "СТАРТ"
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.START)
        def start_session_callback(call):
            player_id = call.from_user.id

            if player_id not in self._chats_statuses.keys():
                self._chats_statuses[player_id] = _Status.IS_NOW_CHAT

            if self._chats_statuses[player_id] == _Status.IS_NOW_CHAT:
                token = self.__create_new_game(player_id)
                self.bot.send_message(player_id, text=f"Токен вашей сессии: {token}")
                log(f"Начата новая сессия {token}")
                log(f"Сессия {token}. Игроки - 1")
            else:
                self.bot.send_message(player_id, text="Вы не можете сейчас начать новую сессию")

        # Обрабатывает нажатие на кнопку "ПРИСОЕДИНИТЬСЯ"
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.JOIN)
        def join_session_callback(call):
            player_id = call.from_user.id

            if player_id not in self._chats_statuses.keys():
                self._chats_statuses[player_id] = _Status.IS_NOW_CHAT

            if self._chats_statuses[player_id] == _Status.IS_NOW_CHAT:
                self.bot.send_message(player_id, text="Введите токен сессии к которой хотите присоедениться или 'нет' "
                                                      "если хотите выйти:")
                self._chats_statuses[player_id] = _Status.IS_NOW_AWAITING_TOKEN
            else:
                self.bot.send_message(player_id, text="Вы не можете сейчас присоедениться к сессии")

        # Обрабатывает нажатие на кнопку хода
        @self.bot.callback_query_handler(func=lambda call: call.data.split(' ')[0] == _CallData.TURN)
        def game_turn_callback(call):
            player_id = call.from_user.id

            if self._chats_statuses[player_id] == _Status.IS_NOW_GAME:
                game: Game = self.__find_game_by_player_id(player_id)

                # После каждого хода экземпляр класса Game самостоятельно меняет роли игроков
                turn_player_id = game.turn_now_player.id
                wait_player_id = game.awaiting_player.id

                if player_id == turn_player_id:
                    turn_res = self.__game_turn(game, player_id, call.data)

                    if turn_res.is_turn_success:
                        message_matrix = self.__matrix_to_emojis(turn_res.matrix)

                        match turn_res.game_result_code:
                            case GameResultCode.GAME_CONTINUE:
                                markup = self.__matrix_to_markup(turn_res.matrix)

                                self.bot.send_message(turn_player_id, f"Результат вашего хода:\n{message_matrix}")
                                self.bot.send_message(turn_player_id, "Ожидайте ход другого игрока...")

                                self.bot.send_message(wait_player_id, "Ваш ход:")
                                self.bot.send_message(wait_player_id, message_matrix, reply_markup=markup)

                            case GameResultCode.NO_ONE_WIN:
                                self.bot.send_message(turn_player_id, f"Ничья:\n{message_matrix}")
                                self.bot.send_message(wait_player_id, f"Ничья:\n{message_matrix}")

                                self.__end_game(game)

                            case GameResultCode.PLAYER_WIN:
                                self.bot.send_message(turn_player_id, f"Результат вашего хода:\n{message_matrix}")
                                self.bot.send_message(turn_player_id, "Вы выиграли")

                                self.bot.send_message(wait_player_id, f"Ход другого игрока:\n{message_matrix}")
                                self.bot.send_message(wait_player_id, "Вы проиграли")

                                self.__end_game(game)
                    else:
                        match turn_res.turn_result_code:
                            case TurnResultCode.INCORRECT_TURN:
                                self.bot.send_message(turn_player_id, "Неправильный ход")
                            case TurnResultCode.NO_PLAYER:
                                self.bot.send_message(turn_player_id, "Не найден игрок")
                            case TurnResultCode.NO_SESSION:
                                self.bot.send_message(turn_player_id, "Не найдена сессия")
                else:
                    self.bot.send_message(wait_player_id, "Ожидайте ваш ход")

    def __create_new_game(self, player_id: int) -> str:
        """
        Создает новую игру с одним игроком

        :param player_id: id игрока
        :return: Токен сессии
        """

        time_based_token = str(int(time.time()))

        game = Game()
        game.start_new_session(player_id, time_based_token)

        self._games.append(game)

        return time_based_token

    @staticmethod
    def __join_to_game(game: Game, player_id: int) -> bool:
        """
        Присоединяет игрока к существующей игре

        :param player_id: id игрока
        :return: True - если попытка присоединения прошла удачно
        """

        is_join_to_session = game.join_to_session(player_id)
        start_matrix = game.start_game()

        if is_join_to_session and start_matrix is not None:
            return True
        else:
            return False

    @staticmethod
    def __game_turn(game: Game, player_id: int, raw_turn: str) -> TurnResult:
        """
        :param game: игра в которой будет сделан ход
        :param player_id: id игрока
        :param raw_turn: строка с информацией о ходе
        :return: Экземпляр класса TurnResult с информацией о результате хода
        """

        turn = [int(i) for i in raw_turn.split(' ')[1:]]
        turn_data = game.make_turn(player_id, turn[0], turn[1])

        return turn_data

    @staticmethod
    def __matrix_to_markup(matrix: [[str]]) -> InlineKeyboardMarkup:
        """
        Преобразование 3х3 матрицы из строк в интерактивную клавиатуру

        :param matrix: двумерный список из строк показывающий текущее состояние игры
        :returns: Экземпляр класса InlineKeyBoardMarkup используемый для создания интерактивной клавиатуры в сообщении
        """

        markup = telebot.types.InlineKeyboardMarkup(row_width=3)

        cell_1_1 = InlineKeyboardButton(matrix[0][0], callback_data=f'{_CallData.TURN} 0 0')
        cell_1_2 = InlineKeyboardButton(matrix[0][1], callback_data=f'{_CallData.TURN} 0 1')
        cell_1_3 = InlineKeyboardButton(matrix[0][2], callback_data=f'{_CallData.TURN} 0 2')
        markup.row(cell_1_1, cell_1_2, cell_1_3)

        cell_2_1 = InlineKeyboardButton(matrix[1][0], callback_data=f'{_CallData.TURN} 1 0')
        cell_2_2 = InlineKeyboardButton(matrix[1][1], callback_data=f'{_CallData.TURN} 1 1')
        cell_2_3 = InlineKeyboardButton(matrix[1][2], callback_data=f'{_CallData.TURN} 1 2')
        markup.row(cell_2_1, cell_2_2, cell_2_3)

        cell_3_1 = InlineKeyboardButton(matrix[2][0], callback_data=f'{_CallData.TURN} 2 0')
        cell_3_2 = InlineKeyboardButton(matrix[2][1], callback_data=f'{_CallData.TURN} 2 1')
        cell_3_3 = InlineKeyboardButton(matrix[2][2], callback_data=f'{_CallData.TURN} 2 2')
        markup.row(cell_3_1, cell_3_2, cell_3_3)

        return markup

    @staticmethod
    def __matrix_to_emojis(matrix: [[str]]) -> str:
        """
        Преобразование 3х3 матрицы из строк в строку сообщения

        :param matrix: двумерный список из строк показывающий текущее состояние игры
        """

        out_str = ""

        for row in matrix:
            row_str = ""

            for cell in row:
                if cell == ' ':
                    row_str += "⬜️"
                elif cell == 'O':
                    row_str += "⭕️"
                elif cell == "X":
                    row_str += "❌"

            row_str += "\n"
            out_str += row_str

        return out_str

    def __find_game_by_player_id(self, player_id: int) -> Game:
        """
        Поиск игры по id участника

        :param player_id: id игрока
        :return: None - если игра не найдена, экземпляр класса Game - если игра найдена
        """

        game = None

        for g in self._games:
            for p in g.players:
                if player_id == p.id:
                    game = g

        return game

    def __find_game_by_session_token(self, session_token: str) -> Game:
        """
        Поиск игры по токену игровой сессии

        :param session_token: токен сессии
        :return: None - если игра не найдена, экземпляр класса Game - если игра найдена
        """

        game = None

        for g in self._games:
            if session_token == g.session_token:
                game = g

        return game

    def __end_game(self, game: Game):
        """
        Заканчивает игровую сессию

        :param game: игра которую требуется завершить
        """

        session_token = game.session_token
        players = game.players

        for pl in players:
            self._chats_statuses[pl.id] = _Status.IS_NOW_CHAT

        for i in range(len(self._games)):
            if self._games[i].session_token == session_token:
                del self._games[i]

    def start(self):
        """
        Запуск бота
        """
        self.bot.infinity_polling()
