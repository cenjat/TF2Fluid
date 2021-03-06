#!/usr/bin/env python
#coding=utf-8
import sys

import paddle.fluid as fluid
from paddle.fluid.initializer import NormalInitializer


class RNNLM(object):
    def __init__(self, config):
        self.parallel = config.parallel
        self.vocab_size = config.vocab_size

        self.embedding_dim = config.embedding_dim
        self.hidden_dim = config.hidden_dim
        self.num_layers = config.num_layers
        self.rnn_model = config.rnn_model

        self.learning_rate = config.learning_rate

    def __input_embedding(self, onehot_word):
        return fluid.layers.embedding(
            input=onehot_word,
            size=[self.vocab_size, self.embedding_dim],
            dtype="float32",
            is_sparse=True)

    def __rnn(self, input):
        for i in range(self.num_layers):
            hidden = fluid.layers.fc(
                size=self.hidden_dim * 4,
                bias_attr=fluid.ParamAttr(
                    initializer=NormalInitializer(loc=0.0, scale=1.0)),
                input=hidden if i else input)
            return fluid.layers.dynamic_lstm(
                input=hidden,
                size=self.hidden_dim * 4,
                candidate_activation="tanh",
                gate_activation="sigmoid",
                cell_activation="sigmoid",
                bias_attr=fluid.ParamAttr(
                    initializer=NormalInitializer(loc=0.0, scale=1.0)),
                is_reverse=False)

    def __cost(self, lstm_output, lbl):
        prediction = fluid.layers.fc(
            input=lstm_output, size=self.vocab_size, act="softmax")
        cost = fluid.layers.cross_entropy(input=prediction, label=lbl)
        cost.stop_gradient = True
        return prediction, cost

    def __network(self, word, lbl):
        word_embedding = self.__input_embedding(word)
        lstm_output = self.__rnn(word_embedding)
        prediction, cost = self.__cost(lstm_output, lbl)
        return prediction, cost

    def build_rnnlm(self):
        word = fluid.layers.data(
            name="current_word", shape=[1], dtype="int64", lod_level=1)
        lbl = fluid.layers.data(
            name="next_word", shape=[1], dtype="int64", lod_level=1)

        if self.parallel:
            places = fluid.layers.get_places()
            pd = fluid.layers.ParallelDo(places)
            with pd.do():
                word_ = pd.read_input(word)
                lbl_ = pd.read_input(lbl)
                prediction, cost = self.__network(word_, lbl_)
                pd.write_output(cost)
                pd.write_output(prediction)
            cost, prediction = pd()
            avg_cost = fluid.layers.mean(x=cost)
        else:
            prediction, avg_cost = self.__network(word, lbl)
        return word, lbl, prediction, avg_cost
