import dataclasses
from enum import IntEnum


class TurnResultCode(IntEnum):
    SUCCESS = 0
    NO_SESSION = 1
    NO_PLAYER = 2
    INCORRECT_TURN = 3


class GameResultCode(IntEnum):
    GAME_CONTINUE = 0
    PLAYER_WIN = 1
    NO_ONE_WIN = 2


@dataclasses.dataclass
class Player:
    """
    Данные об игроке:\n
    sign: str - символ за который играет игрок (X или O)\n
    id: int - id игрока
    :param sign:
    """
    sign: str
    id: int


@dataclasses.dataclass
class TurnResult:
    """
    Данные о ходе:\n
    is_turn_success: bool - успешен ли ход\n
    game_code: GameResultCode - код сообщения о состоянии игры\n
    turn_result_code: TurnResultCode - код сообщения о результате хода\n
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

    @property
    def game_matrix(self) -> [[str]]:
        return self.matrix

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

                is_player_win = self.__is_player_win(self.matrix)
                is_matrix_full = self.__is_matrix_full(self.matrix)

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
    def __is_player_win(matrix: [[str]]) -> bool:
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
    def __is_matrix_full(matrix: [[str]]) -> bool:
        for row in matrix:
            if " " in row:
                return False
        return True
