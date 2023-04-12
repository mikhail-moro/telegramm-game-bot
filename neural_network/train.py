import numpy as np

from keras.models import Sequential, save_model
from keras.layers import Dense, Activation, Flatten
from keras.optimizers import Adam

from rl.agents.dqn import DQNAgent
from rl.policy import EpsGreedyQPolicy
from rl.memory import SequentialMemory

from env import TicTacToe
from agent import InterleavedAgent


env = TicTacToe()
np.random.seed(123)
nb_actions = env.action_space.n


def make_dqn():
    model = Sequential()
    model.add(Flatten(input_shape=(1,) + env.observation_space.shape))
    model.add(Activation('relu'))
    model.add(Dense(27))
    model.add(Activation('relu'))
    model.add(Dense(27))
    model.add(Activation('relu'))
    model.add(Dense(27))
    model.add(Activation('relu'))
    model.add(Dense(nb_actions))
    model.add(Activation('linear'))

    memory = SequentialMemory(limit=50000, window_length=1)
    policy = EpsGreedyQPolicy(eps=0.2)

    dqn = DQNAgent(
        model=model,
        nb_actions=nb_actions,
        memory=memory,
        nb_steps_warmup=100,
        target_model_update=1e-2,
        policy=policy
    )

    dqn.compile(Adam(lr=1e-3), metrics=['mae'])

    return dqn


dqn_agent = make_dqn()
agent = InterleavedAgent([dqn_agent, dqn_agent])

agent.compile(Adam(lr=1e-3), metrics=['mae'])
agent.fit(env, nb_steps=100000, visualize=False, verbose=1)

save_model(dqn_agent.model, 'tic-tac-toe_model.h5')