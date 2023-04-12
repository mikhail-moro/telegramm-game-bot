import numpy as np

from gym import Env, spaces


# Список паттернов которые означают, то что один из игроков выиграл
win_patterns = [
    [0, 1, 2],
    [3, 4, 5],
    [6, 7, 8],
    [0, 3, 6],
    [1, 4, 7],
    [2, 5, 8],
    [0, 4, 8],
    [2, 4, 6]
]


class TicTacToe(Env):
    action_space = spaces.Discrete(9)
    observation_space = spaces.MultiDiscrete([2 for _ in range(0, 9 * 3)])

    def __init__(self):
        self.current_player = 0
        self.game_field = np.zeros(9, dtype="int")

    def _is_field_empty(self):
        for i in self.game_field:
            if i != 0:
                return False
        return True

    def _one_hot_board(self):
        #
        # Переводим доску в бинарный вектор, для разных игроков вектор будет выглядеть по-разному, так как модель
        # обучаемая в этой среде ходит за 2-х игроков по-очереди, следовательно необходимо менять 1->2 и 2->1
        #
        if self.current_player == 0:
            return np.eye(3)[self.game_field].reshape(-1)

        if self.current_player == 1:
            return np.eye(3)[self.game_field][:, [0, 2, 1]].reshape(-1)

    def _is_player_win(self):
        for pattern in win_patterns:
            sign = self.current_player+1
            value = self.game_field[pattern]

            if value[0] == sign and value[1] == sign and value[2] == sign:
                return True
        return False

    def _is_player_can_lose(self):
        for pattern in win_patterns:
            sign = 2 - self.current_player
            value = self.game_field[pattern]

            if value[0] == 0 and value[1] == sign and value[2] == sign:
                return True
            if value[0] == sign and value[1] == 0 and value[2] == sign:
                return True
            if value[0] == sign and value[1] == sign and value[2] == 0:
                return True
        return False

    def _is_field_full(self):
        for i in self.game_field:
            if i == 0:
                return False
        return True

    def reset(self):
        self.current_player = 0
        self.game_field = np.zeros(9, dtype="int")

        return self._one_hot_board()

    def step(self, action):
        if self.game_field[action] == 0:
            #
            # Первый игрок обозначается 0, а второй 1, следовательно ходить они будут 1 и 2 или 0+1 и 1+1, соответсвенно
            #
            self.game_field[action] = self.current_player + 1

            if self._is_player_win():
                #
                # Игрок победил
                #
                return self._one_hot_board(), 2, True, {}
            elif self._is_field_full():
                #
                # Ничья
                #
                return self._one_hot_board(), 0, True, {}
            elif self._is_player_can_lose():
                #
                # Игрок не проиграл, но походил так, что на следующем ходу может быть побеждён, игра продолжается
                #
                old_board = self._one_hot_board()

                # Меняем игрока
                self.current_player = 1 - self.current_player

                return old_board, -2, False, {}
            else:
                #
                # Игрок просто походил, игра продолжается
                #
                old_board = self._one_hot_board()

                # Меняем игрока
                self.current_player = 1 - self.current_player

                return old_board, 0, False, {}
        else:
            #
            # Игрок походил в занятую ячейку
            #
            return self._one_hot_board(), -10, True, {}

    def render(self, mode='human'):
        pass