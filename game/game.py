import dataclasses
from enum import IntEnum

import keras
import numpy as np
from keras import Sequential


class TurnResultCode(IntEnum):
    SUCCESS = 0
    NO_SESSION = 1
    NO_PLAYER = 2
    INCORRECT_TURN = 3


class GameResultCode(IntEnum):
    GAME_CONTINUE = 0
    PLAYER_WIN = 1
    NO_ONE_WIN = 2
    AI_WIN = 3


@dataclasses.dataclass
class Player:
    """
    Данные об игроке:
    sign: str - символ за который играет игрок (X или O)
    id: int - id игрока
    """
    sign: str
    id: int


@dataclasses.dataclass
class TurnResult:
    """
    Данные о ходе:
    is_turn_success: bool - успешен ли ход
    game_code: GameResultCode - код сообщения о состоянии игры
    turn_result_code: TurnResultCode - код сообщения о результате хода
    matrix: [[str]] - двумерный список из строк показывающий текущее состояние игры
    """
    is_turn_success: bool
    game_result_code: GameResultCode
    turn_result_code: TurnResultCode
    matrix: [[str]]


class Game:
    matrix: [[str]] = None
    turn: str = None
    session_token: str = None
    players: [Player] = []

    _is_session_active = False
    _is_game_active = False

    @property
    def turn_now_player(self) -> Player:
        for pl in self.players:
            if self.turn == pl.sign:
                return pl

    @property
    def awaiting_player(self) -> Player:
        for pl in self.players:
            if self.turn != pl.sign:
                return pl

    def is_player_in_game(self, player_id: int) -> bool:
        for pl in self.players:
            if pl.id == player_id:
                return True

        return False

    def start_new_session(self, player_id: int, session_token: str):
        self.session_token = session_token
        self.matrix = [[" ", " ", " "],
                       [" ", " ", " "],
                       [" ", " ", " "]]

        player = Player("X", player_id)
        self.players.append(player)
        self.turn = "X"
        self._is_session_active = True

    def join_to_session(self, player_id: int) -> bool:
        if self._is_session_active:
            player = Player("O", player_id)
            self.players.append(player)

            return True
        else:
            return False

    def start_game(self) -> [[str]]:
        if self._is_session_active:
            self._is_game_active = True

            return self.matrix
        else:
            return None

    def make_turn(self, player_id: int, row: int, column: int) -> TurnResult:
        if not self._is_session_active:
            return TurnResult(False, GameResultCode.GAME_CONTINUE, TurnResultCode.NO_SESSION, None)

        player = None
        for pl in self.players:
            if pl.id == player_id:
                player = pl

        if player is None:
            return TurnResult(False, GameResultCode.GAME_CONTINUE, TurnResultCode.NO_PLAYER, None)

        if row in [0, 1, 2] and column in [0, 1, 2]:
            cell = self.matrix[row][column]

            if cell == " ":
                self.matrix[row][column] = player.sign

                if player.sign == "X":
                    self.turn = "O"
                else:
                    self.turn = "X"

                is_player_win = self._is_player_win(self.matrix)
                is_matrix_full = self._is_matrix_full(self.matrix)

                if is_player_win:
                    game_result = GameResultCode.PLAYER_WIN
                elif is_matrix_full:
                    game_result = GameResultCode.NO_ONE_WIN
                else:
                    game_result = GameResultCode.GAME_CONTINUE

                return TurnResult(True, game_result, TurnResultCode.SUCCESS, self.matrix)
            else:
                return TurnResult(False, GameResultCode.GAME_CONTINUE, TurnResultCode.INCORRECT_TURN, self.matrix)
        else:
            return TurnResult(False, GameResultCode.GAME_CONTINUE, TurnResultCode.INCORRECT_TURN, self.matrix)

    @staticmethod
    def _is_player_win(matrix: [[str]]) -> bool:
        for sign in ["X", "O"]:
            if matrix[0][0] == sign and matrix[0][1] == sign and matrix[0][2] == sign:
                return True
            if matrix[1][0] == sign and matrix[1][1] == sign and matrix[1][2] == sign:
                return True
            if matrix[2][0] == sign and matrix[2][1] == sign and matrix[2][2] == sign:
                return True

            if matrix[0][0] == sign and matrix[1][0] == sign and matrix[2][0] == sign:
                return True
            if matrix[0][1] == sign and matrix[1][1] == sign and matrix[2][1] == sign:
                return True
            if matrix[0][2] == sign and matrix[1][2] == sign and matrix[2][2] == sign:
                return True

            if matrix[0][0] == sign and matrix[1][1] == sign and matrix[2][2] == sign:
                return True
            if matrix[0][2] == sign and matrix[1][1] == sign and matrix[2][0] == sign:
                return True

        return False

    @staticmethod
    def _is_matrix_full(matrix: [[str]]) -> bool:
        for row in matrix:
            if " " in row:
                return False
        return True


class GameAI:
    def __init__(self, model: Sequential):
        self.player = None
        self.matrix = None
        self.model: Sequential = model

    def start_new_session(self, player_id: int):
        self.matrix: [[str]] = [[" ", " ", " "],
                                [" ", " ", " "],
                                [" ", " ", " "]]
        self.player: Player = Player('X', player_id)

    def _one_hot(self):
        field = np.zeros(9, dtype='int')

        for i in range(3):
            for a in range(3):
                if self.matrix[i][a] == 'X':
                    field[i*a] = 1
                if self.matrix[i][a] == 'O':
                    field[i*a] = 2

        return np.eye(3)[field][:, [0, 2, 1]].reshape(-1)

    def make_turn(self, row: int, column: int) -> TurnResult:
        #
        # Ход человека
        #
        if row in [0, 1, 2] and column in [0, 1, 2]:
            cell = self.matrix[row][column]

            if cell == ' ':
                self.matrix[row][column] = 'X'

                is_player_win = self._is_player_win()
                is_matrix_full = self._is_matrix_full()

                if is_player_win or is_matrix_full:
                    if is_player_win:
                        return TurnResult(True, GameResultCode.PLAYER_WIN, TurnResultCode.SUCCESS, self.matrix)
                    else:
                        return TurnResult(True, GameResultCode.NO_ONE_WIN, TurnResultCode.SUCCESS, self.matrix)
                else:
                    #
                    # Ход AI
                    #
                    predicted = self.model.predict([self._one_hot().reshape(1, 1, 27)], verbose=0)
                    checked_predicted = []

                    for i in range(3):
                        for a in range(3):
                            if self.matrix[i][a] == ' ':
                                checked_predicted.append(predicted[0][i*a])
                            else:
                                checked_predicted.append(-100)

                    turn = np.argmax(checked_predicted)
                    turn = (int(turn / 3), turn % 3)

                    self.matrix[turn[0]][turn[1]] = 'O'

                    if is_player_win or is_matrix_full:
                        if is_player_win:
                            return TurnResult(True, GameResultCode.AI_WIN, TurnResultCode.SUCCESS, self.matrix)
                        else:
                            return TurnResult(True, GameResultCode.NO_ONE_WIN, TurnResultCode.SUCCESS, self.matrix)
                    else:
                        return TurnResult(True, GameResultCode.GAME_CONTINUE, TurnResultCode.SUCCESS, self.matrix)
            else:
                return TurnResult(False, GameResultCode.GAME_CONTINUE, TurnResultCode.INCORRECT_TURN, self.matrix)
        else:
            return TurnResult(False, GameResultCode.GAME_CONTINUE, TurnResultCode.INCORRECT_TURN, self.matrix)

    def _is_player_win(self) -> bool:
        for sign in ["X", "O"]:
            if self.matrix[0][0] == sign and self.matrix[0][1] == sign and self.matrix[0][2] == sign:
                return True
            if self.matrix[1][0] == sign and self.matrix[1][1] == sign and self.matrix[1][2] == sign:
                return True
            if self.matrix[2][0] == sign and self.matrix[2][1] == sign and self.matrix[2][2] == sign:
                return True

            if self.matrix[0][0] == sign and self.matrix[1][0] == sign and self.matrix[2][0] == sign:
                return True
            if self.matrix[0][1] == sign and self.matrix[1][1] == sign and self.matrix[2][1] == sign:
                return True
            if self.matrix[0][2] == sign and self.matrix[1][2] == sign and self.matrix[2][2] == sign:
                return True

            if self.matrix[0][0] == sign and self.matrix[1][1] == sign and self.matrix[2][2] == sign:
                return True
            if self.matrix[0][2] == sign and self.matrix[1][1] == sign and self.matrix[2][0] == sign:
                return True

        return False

    def _is_matrix_full(self) -> bool:
        for row in self.matrix:
            if " " in row:
                return False
        return True

    @staticmethod
    def _to_int(char: str) -> float:
        match char:
            case ' ':
                return 0.0
            case 'X':
                return 1/3
            case 'O':
                return 2/3

    def _reshape(self) -> [[float]]:
        out_matrix = []

        for i in self.matrix:
            out_matrix.append([self._to_int(a) for a in i])

        return out_matrix
