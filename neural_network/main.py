# --------------------------------------------------------------------------
# Информация по созданию и обучению модели была во многом с̶т̶ы̶р̶е̶н̶а̶
# адаптированна из следующего материала:
#   https://mahowald.github.io/deep-tictactoe/
# --------------------------------------------------------------------------

# Данная модель также реализована в Google Collab:
#   https://colab.research.google.com/drive/1DN1RjyfSvlEkuXEKjmdENCG8gbMwg5XY?usp=sharing

# Данная модель на Keras состоит из четырех полносвязных (Dense) слоев.
# Между слоями используется функция активации ReLU, кроме последнего слоя,
# который использует линейную функцию активации
#
# Обучение происходило по принципу обучения с подкреплением (Reinforcement
# learning) по алгоритму DQN - Deep Q Network
#
# Приведенный ниже пример выводит предсказанный моделью лучший ход, для
# состояния игры в переменной game_field
#
# Обозначения:
#   0 - '_'
#   1 - 'X'
#   2 - 'O'
#
# Данный пример расчитан, на то что модель будет ходить первой (хотя в боте она
# всегда ходит второй), то есть, за X. Для того чтобы нейросеть ходила
# второй, и как следствие за O, необходимо поменять функцию one_hot_decode
# изменив вектор получаемый в результате "горячей" кодировки (перед кодировкой
# поменять в входной матрице 1 на 2 и 2 на 1)
#


import numpy as np
from keras.models import load_model

if __name__ == "__main__":
    # Преобразует массив описывающий состояние игрового поля, в двоичный вектор
    # длиной 3*9
    def one_hot_decode(field):
        return np.eye(3)[field].reshape(-1)

    # состояние игрового поля
    game_field = np.array([
        0, 0, 0,
        0, 0, 0,
        0, 0, 0
    ])

    # загрузка заранее обученной модели
    model = load_model('tic-tac-toe_model.h5')

    # получаем выходной вектор модели
    predict_vector = model.predict(one_hot_decode(game_field).reshape(1, 1, 27), verbose=0)

    # меняем состояние игрового поля
    game_field[np.argmax(predict_vector)] = 1

    out_str = "Ход модели:\n"

    for i in range(9):
        if game_field[i] == 0:
            out_str += '_ '

        if game_field[i] == 1:
            out_str += 'X '

        if game_field[i] == 2:
            out_str += 'O '

        if (i + 1) % 3 == 0:
            out_str += '\n'

    print(out_str)
